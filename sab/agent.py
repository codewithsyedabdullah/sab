from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Config
from .llm import LLM
from .tools import ALL_TOOLS, Tool
from .tools import file_tools

SYSTEM_PROMPT = """Your name is SAB. You are an AI coding agent. You were created by Syed Abdullah Yaqoob. NEVER say you were made by Alibaba, Qwen, or any other company. If asked who made you, always say "Syed Abdullah Yaqoob."

You help users with software engineering tasks using code tools.

Rules:
1. Your name is SAB. You were made by Syed Abdullah.
2. Always read a file before editing it.
3. Make minimal, focused changes.
4. Use run_shell to execute code, run tests, install packages.
5. Use grep/glob to find files and code patterns.
6. If something fails, diagnose and try again.
7. Never commit secrets or API keys.

Current workspace: {workspace}
"""


class Agent:
    def __init__(self, config: Config, endpoint: dict | None = None, history: list[dict] | None = None):
        self.config = config
        self.llm = LLM(config.llm, override=endpoint)
        self.endpoint = endpoint or {}
        self.tools: dict[str, Tool] = {t.name: t for t in ALL_TOOLS}
        self.messages: list[dict[str, str]] = []
        self._init_messages()
        self._seed_history(history)

    def _seed_history(self, history: list[dict] | None):
        if not history:
            return
        # Rebuild the full conversation (including tool_calls + tool result
        # rounds) so the model remembers not just what was said, but what it
        # actually did on disk. History entries may carry structured
        # tool_calls/name/arguments alongside role+content (see agent.dump_history).
        for h in history:
            role = h.get("role")
            if role == "assistant" and h.get("tool_calls"):
                calls = []
                for tc in h["tool_calls"]:
                    fn = tc.get("function") or {}
                    arg = fn.get("arguments")
                    if isinstance(arg, str):
                        try:
                            arg = json.loads(arg)
                        except (json.JSONDecodeError, TypeError):
                            arg = {}
                    calls.append({
                        "id": tc.get("id") or f"call_{len(calls)}",
                        "type": "function",
                        "function": {"name": fn.get("name", ""), "arguments": json.dumps(arg)},
                    })
                if calls:
                    self.messages.append({
                        "role": "assistant",
                        "content": h.get("content") or "",
                        "tool_calls": calls,
                    })
                    continue
            if role == "tool":
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": h.get("tool_call_id") or "",
                    "content": h.get("content") or "",
                })
                continue
            if role in ("user", "assistant"):
                self.messages.append({"role": role, "content": h.get("content") or ""})

    def dump_history(self, max_turns: int = 0) -> list[dict]:
        # Serialize the conversation (minus the system prompt) for persistence.
        # Tool-call rounds are kept structured so a later run can restore them.
        out = []
        for m in self.messages:
            if m.get("role") == "system":
                continue
            if m.get("role") == "assistant" and m.get("tool_calls"):
                out.append({
                    "role": "assistant",
                    "content": m.get("content") or "",
                    "tool_calls": m["tool_calls"],
                })
            else:
                out.append({"role": m.get("role"), "content": m.get("content") or ""})
        if max_turns > 0 and len(out) > max_turns:
            out = out[-max_turns:]
        return out

    def _init_messages(self):
        system = SYSTEM_PROMPT.format(workspace=str(self.config.workspace))
        self.messages = [{"role": "system", "content": system}]

    def _get_tool_schemas(self) -> list[dict]:
        if not self.config.agent.use_tools:
            return []
        return [t.to_schema() for t in self.tools.values()]

    def _execute_tool(self, name: str, arguments: dict) -> str:
        tool = self.tools.get(name)
        if not tool:
            return f"Unknown tool: {name}"

        file_tools._active_workspace = str(self.config.workspace)
        try:
            result = tool.run(**arguments)
        finally:
            file_tools._active_workspace = None

        if result.success:
            return result.output
        return f"Error: {result.error}\n{result.output}" if result.output else f"Error: {result.error}"

    def run(self, user_message: str, on_thinking: Any = None, on_tool: Any = None) -> str:
        self.messages.append({"role": "user", "content": user_message})

        tool_schemas = self._get_tool_schemas()

        for iteration in range(self.config.agent.max_iterations):
            response = self.llm.chat(self.messages, tools=tool_schemas or None)

            if response.get("tool_calls"):
                self.messages.append({
                    "role": "assistant",
                    "content": response["content"] or "",
                    "tool_calls": [
                        {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                        for tc in response["tool_calls"]
                    ],
                })

                for tc in response["tool_calls"]:
                    if on_tool:
                        on_tool(tc["name"], tc["arguments"])
                    output = self._execute_tool(tc["name"], tc["arguments"])
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": output,
                    })
            else:
                content = response["content"] or ""
                self.messages.append({"role": "assistant", "content": content})
                return content

        return "Reached max iterations. Stopping."

    def run_stream(self, user_message: str, on_tool: Any = None):
        """Yield events: content chunks, tool calls, tool results."""
        self.messages.append({"role": "user", "content": user_message})

        tool_schemas = self._get_tool_schemas()

        for iteration in range(self.config.agent.max_iterations):
            full_content = ""
            tool_calls = None

            for event in self.llm.chat_stream(self.messages, tools=tool_schemas or None):
                if event["type"] == "content":
                    full_content += event["text"]
                    yield {"type": "content", "text": event["text"]}
                elif event["type"] == "tool_calls":
                    tool_calls = event["calls"]

            if tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": full_content,
                    "tool_calls": [
                        {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                        for tc in tool_calls
                    ],
                })

                for tc in tool_calls:
                    if on_tool:
                        on_tool(tc["name"], tc["arguments"])

                    yield {"type": "tool_start", "name": tc["name"], "arguments": tc["arguments"]}
                    output = self._execute_tool(tc["name"], tc["arguments"])
                    yield {"type": "tool_result", "name": tc["name"], "output": output}

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": output,
                    })
            else:
                self.messages.append({"role": "assistant", "content": full_content})
                yield {"type": "done"}
                return

        yield {"type": "done", "error": "Max iterations reached"}

    def reset(self):
        self._init_messages()

    def save_session(self, path: str):
        session_path = Path(path)
        session_path.mkdir(parents=True, exist_ok=True)
        (session_path / "messages.json").write_text(
            json.dumps(self.messages, indent=2), encoding="utf-8"
        )

    def load_session(self, path: str) -> bool:
        session_file = Path(path) / "messages.json"
        if session_file.exists():
            self.messages = json.loads(session_file.read_text(encoding="utf-8"))
            return True
        return False
