from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from .base import Tool, ToolResult


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents using regex. Returns matching lines with file paths and line numbers."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
            "include": {"type": "string", "description": "File pattern to include (e.g. '*.py')"},
        },
        "required": ["pattern"],
    }

    def run(self, pattern: str, path: str = ".", include: str = "", **kwargs) -> ToolResult:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            search_path = Path(path).resolve()
            results: list[str] = []

            if search_path.is_file():
                files = [search_path]
            else:
                files = [
                    f for f in search_path.rglob("*")
                    if f.is_file()
                    and not any(d in f.parts for d in [".git", "node_modules", "__pycache__", ".venv"])
                    and (not include or fnmatch.fnmatch(f.name, include))
                ]

            for f in files[:500]:
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            rel = f.relative_to(search_path) if search_path.is_dir() else f
                            results.append(f"{rel}:{i}: {line.strip()}")
                            if len(results) >= 100:
                                break
                except Exception:
                    continue
                if len(results) >= 100:
                    break

            if not results:
                return ToolResult(success=True, output="No matches found")
            return ToolResult(success=True, output="\n".join(results))
        except re.error as e:
            return ToolResult(success=False, output="", error=f"Invalid regex: {e}")


class GlobTool(Tool):
    name = "glob"
    description = "Find files matching a glob pattern. Returns matching file paths."
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')"},
            "path": {"type": "string", "description": "Directory to search in", "default": "."},
        },
        "required": ["pattern"],
    }

    def run(self, pattern: str, path: str = ".", **kwargs) -> ToolResult:
        try:
            search_path = Path(path).resolve()
            matches = [
                str(f.relative_to(search_path))
                for f in search_path.glob(pattern)
                if f.is_file()
                and not any(d in f.parts for d in [".git", "node_modules", "__pycache__", ".venv"])
            ]

            if not matches:
                return ToolResult(success=True, output="No files matched")
            return ToolResult(success=True, output="\n".join(sorted(matches[:200])))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
