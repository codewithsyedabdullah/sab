from __future__ import annotations

import json
from typing import Any, Generator

import requests

from .config import LLMConfig

OLLAMA_DEFAULT = "http://localhost:11434"


class LLM:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._api_base = config.base_url or OLLAMA_DEFAULT

    def _messages_payload(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict:
        payload: dict[str, Any] = {
            "model": self.config.model,
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
        payload = self._messages_payload(messages, tools)
        payload["stream"] = False

        resp = requests.post(f"{self._api_base}/api/chat", json=payload, timeout=300)
        resp.raise_for_status()
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
        payload = self._messages_payload(messages, tools)

        resp = requests.post(
            f"{self._api_base}/api/chat", json=payload, stream=True, timeout=300
        )
        resp.raise_for_status()

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
