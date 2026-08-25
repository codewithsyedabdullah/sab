from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "qwen2.5:0.5b"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.1
    max_tokens: int = 4096


@dataclass
class AgentConfig:
    max_iterations: int = 50
    max_file_size: int = 1_000_000
    use_tools: bool = False
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
        ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
        ".rs", ".go", ".java", ".c", ".cpp", ".h",
        ".sh", ".bash", ".ps1",
    ])
    blocked_directories: list[str] = field(default_factory=lambda: [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", ".cache",
    ])


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    workspace: Path = field(default_factory=lambda: Path.cwd())

    @classmethod
    def from_env(cls) -> Config:
        provider = os.getenv("SAB_PROVIDER", "ollama")
        model = os.getenv("SAB_MODEL", "qwen2.5:0.5b")
        api_key = os.getenv("SAB_API_KEY", "")
        base_url = os.getenv("SAB_BASE_URL", "")

        return cls(
            llm=LLMConfig(
                provider=provider,
                model=model,
                api_key=api_key,
                base_url=base_url,
            ),
            workspace=Path(os.getenv("SAB_WORKSPACE", Path.cwd())),
        )
