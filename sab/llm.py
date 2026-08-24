from __future__ import annotations

import json
from typing import Any

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
