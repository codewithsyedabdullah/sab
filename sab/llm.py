from __future__ import annotations

import json
from typing import Any, Generator

import requests

from .config import LLMConfig

OLLAMA_DEFAULT = "http://localhost:11434"


def _clean_url(base: str) -> str:
    return str(base or "").rstrip("/")


class LLM:
    def __init__(self, config: LLMConfig, override: dict | None = None):
        self.config = config
        self._api_base = config.base_url or OLLAMA_DEFAULT
        self._model = config.model
        self._api_key: str | None = None
        self._openai_compat = False

        if override:
            ob = override.get("base_url") or override.get("url")
            if ob:
                self._api_base = _clean_url(ob)
            if override.get("model"):
                self._model = override["model"]
            self._api_key = (override.get("api_key") or "").strip() or None
            kind = str(override.get("kind") or override.get("endpoint_kind") or "").lower()
            if kind in ("api", "openai", "proxy"):
                self._openai_compat = True

    # ------------------------------------------------------------------
    # OpenAI-compatible (v1/chat/completions)
    # ------------------------------------------------------------------
    def _openai_url(self) -> str:
        base = self._api_base
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1") or base.endswith("/v1/"):
            return base.rstrip("/") + "/chat/completions"
        return base + "/v1/chat/completions"

    def _raise_for(self, resp) -> None:
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            detail = ""
            try:
                body = resp.json()
                err = body.get("error") or {}
                if isinstance(err, dict):
                    detail = err.get("message") or ""
                else:
                    detail = str(err)
            except Exception:
                detail = (resp.text or "")[:300]
            msg = f"LLM request failed ({resp.status_code})"
            if detail:
                msg += f": {detail}"
            raise RuntimeError(msg) from e

    def _resolve_tool_calls(self, choices) -> list[dict] | None:
        delta = choices or {}
        tcs = delta.get("tool_calls") or []
        if not tcs:
            return None
        calls = []
        buf: dict[str, dict] = {}
        order: list[str] = []
        for tc in tcs:
            tid = tc.get("id") or tc.get("index") or ""
            fn = tc.get("function") or {}
            if tid not in buf:
                buf[tid] = {"id": f"call_{len(order)}", "name": "", "arguments": ""}
                order.append(tid)
            if fn.get("name"):
                buf[tid]["name"] += fn["name"]
            if fn.get("arguments"):
                buf[tid]["arguments"] += fn["arguments"]
        for tid in order:
            entry = buf[tid]
            args = entry["arguments"]
            try:
                entry["arguments"] = json.loads(args) if args else {}
            except (json.JSONDecodeError, TypeError):
                entry["arguments"] = {}
            calls.append(entry)
        return calls

    def openai_chat(
        self, messages: list[dict[str, str]], tools: list[dict] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(self._openai_url(), json=payload, headers=headers, timeout=300)
        self._raise_for(resp)
        data = resp.json()
        choices = (data.get("choices") or [{}])[0] or {}
        msg = choices.get("message") or {}
        result: dict[str, Any] = {"content": msg.get("content") or data.get("content") or ""}
        tcs = msg.get("tool_calls") or []
        if tcs:
            calls = []
            for tc in tcs:
                fn = tc.get("function") or {}
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                calls.append({
                    "id": tc.get("id") or f"call_{id(tc)}",
                    "name": fn.get("name", ""),
                    "arguments": args,
                })
            result["tool_calls"] = calls
        return result

    def openai_chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        payload: dict[str, Any] = {"model": self._model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            resp = requests.post(self._openai_url(), json=payload, headers=headers, stream=True, timeout=300)
        except requests.RequestException as e:
            raise RuntimeError(f"LLM request failed: {e}") from e
        try:
            self._raise_for(resp)
        except RuntimeError as e:
            # Some gateways reject `stream: true` outright ("streaming is not
            # supported"). Retry once without streaming so those providers still
            # work. Narrowly scoped to bodies that say streaming is unavailable
            # so we never double-fire a request a provider already accepted.
            msg = str(e).lower()
            refuses_stream = any(w in msg for w in (
                "not support", "unsupported", "not enabled", "disabled",
                "not available", "cannot", "does not support", "stream is not",
                "streaming is not", "no streaming", "doesn't support"))
            if "stream" in msg and refuses_stream:
                result = self.openai_chat(messages, tools)
                if result.get("content"):
                    yield {"type": "content", "text": result["content"]}
                if result.get("tool_calls"):
                    yield {"type": "tool_calls", "calls": result["tool_calls"]}
                return
            raise

        tool_acc: dict[int, dict] = {}
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line or line.startswith(":") or line.startswith("event:"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            if line == "[DONE]":
                break
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                # Some lightweight gateways stream the bare text itself.
                if line and len(line) < 4000:
                    yield {"type": "content", "text": line + "\n"}
                continue
            if isinstance(chunk, dict) and chunk.get("error"):
                err = chunk["error"]
                yield {"type": "error", "message": err.get("message") if isinstance(err, dict) else str(err)}
                return
            if isinstance(chunk, list):
                chunk = chunk[0] if chunk else {}
            if not isinstance(chunk, dict):
                continue
            # Bare-content gateway style (no choices wrapper).
            if "content" in chunk:
                yield {"type": "content", "text": str(chunk.get("content", ""))}
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0] or {}
            part = choice.get("delta") or choice.get("message") or {}
            if part.get("content"):
                yield {"type": "content", "text": part["content"]}
            elif choice.get("text"):
                yield {"type": "content", "text": choice["text"]}
            tcs = part.get("tool_calls") or choice.get("tool_calls")
            if tcs:
                for tc in tcs:
                    idx = tc.get("index", 0)
                    fn = tc.get("function") or {}
                    acc = tool_acc.setdefault(idx, {"id": f"call_{idx}", "name": "", "arguments": ""})
                    if fn.get("name"):
                        acc["name"] += fn["name"]
                    if fn.get("arguments"):
                        acc["arguments"] += fn["arguments"]
            if choice.get("finish_reason"):
                pass
        if tool_acc:
            calls = []
            for idx in sorted(tool_acc.keys()):
                entry = tool_acc[idx]
                try:
                    entry["arguments"] = json.loads(entry["arguments"]) if entry["arguments"] else {}
                except (json.JSONDecodeError, TypeError):
                    entry["arguments"] = {}
                calls.append(entry)
            yield {"type": "tool_calls", "calls": calls}

    # ------------------------------------------------------------------
    # Unified entry points (used by Agent)
    # ------------------------------------------------------------------
    def _messages_payload(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools
        return payload

    def chat(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict[str, Any]:
        if self._openai_compat:
            return self.openai_chat(messages, tools)
        payload = self._messages_payload(messages, tools)
        payload["stream"] = False

        resp = requests.post(f"{self._api_base}/api/chat", json=payload, timeout=300)
        self._raise_for(resp)
        data = resp.json()

        msg = data.get("message", {})
        result: dict[str, Any] = {"content": msg.get("content", "")}

        tool_calls_raw = msg.get("tool_calls")
        if tool_calls_raw:
            result["tool_calls"] = []
            for tc in tool_calls_raw:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                result["tool_calls"].append({
                    "id": f"call_{id(tc)}",
                    "name": fn.get("name", ""),
                    "arguments": args,
                })

        return result

    def chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        if self._openai_compat:
            yield from self.openai_chat_stream(messages, tools)
            return
        payload = self._messages_payload(messages, tools)

        resp = requests.post(
            f"{self._api_base}/api/chat", json=payload, stream=True, timeout=300
        )
        self._raise_for(resp)

        tool_calls_buffer: dict[int, dict] = {}

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = chunk.get("message", {})
            content = msg.get("content", "")
            if content:
                yield {"type": "content", "text": content}

            ollama_tool_calls = msg.get("tool_calls")
            if ollama_tool_calls:
                for tc in ollama_tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "")
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                    idx = len(tool_calls_buffer)
                    tool_calls_buffer[idx] = {
                        "id": f"call_{idx}",
                        "name": name,
                        "arguments": args,
                    }

            if chunk.get("done"):
                break

        if tool_calls_buffer:
            calls = []
            for idx in sorted(tool_calls_buffer.keys()):
                calls.append(tool_calls_buffer[idx])
            yield {"type": "tool_calls", "calls": calls}

    def chat_stream_no_tools(
        self, messages: list[dict[str, str]]
    ) -> Generator[dict[str, Any], None, None]:
        yield from self.chat_stream(messages, tools=None)
