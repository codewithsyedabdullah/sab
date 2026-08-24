from __future__ import annotations

import json
from typing import Any, Generator

import litellm

from .config import LLMConfig

litellm.drop_params = True


class LLM:
    def __init__(self, config: LLMConfig):
        self.config = config
        self._configure()

    def _configure(self):
        if self.config.provider == "ollama":
            self.model = f"ollama/{self.config.model}"
            if self.config.base_url:
                litellm.api_base = self.config.base_url
        elif self.config.provider == "anthropic":
            self.model = f"anthropic/{self.config.model}"
            litellm.api_key = self.config.api_key
        elif self.config.provider == "openai":
            self.model = f"openai/{self.config.model}"
            litellm.api_key = self.config.api_key
        else:
            self.model = self.config.model

    def chat(self, messages: list[dict[str, str]], tools: list[dict] | None = None) -> dict[str, Any]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = litellm.completion(**kwargs)
        choice = response.choices[0]

        result: dict[str, Any] = {"content": choice.message.content or ""}

        if hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            result["tool_calls"] = []
            for tc in choice.message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                })

        return result

    def chat_stream(
        self, messages: list[dict[str, str]], tools: list[dict] | None = None
    ) -> Generator[dict[str, Any], None, None]:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        tool_calls_buffer: dict[int, dict] = {}

        for chunk in litellm.completion(**kwargs, stream=True):
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                yield {"type": "content", "text": delta.content}

            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_calls_buffer[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_buffer[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments

        if tool_calls_buffer:
            calls = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": args,
                })
            yield {"type": "tool_calls", "calls": calls}
