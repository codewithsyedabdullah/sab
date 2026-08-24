from __future__ import annotations

from pathlib import Path

from .base import Tool, ToolResult


class FileReadTool(Tool):
    name = "read_file"
    description = "Read the contents of a file. Returns the full file content with line numbers."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to read"},
            "offset": {"type": "integer", "description": "Line number to start from (0-indexed)", "default": 0},
            "limit": {"type": "integer", "description": "Max lines to read", "default": 2000},
        },
        "required": ["path"],
    }

    def run(self, path: str, offset: int = 0, limit: int = 2000, **kwargs) -> ToolResult:
        try:
            p = Path(path).resolve()
            if not p.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")
            if not p.is_file():
                return ToolResult(success=False, output="", error=f"Not a file: {path}")
            if p.stat().st_size > 1_000_000:
                return ToolResult(success=False, output="", error="File too large (>1MB)")

            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            selected = lines[offset : offset + limit]
            numbered = [f"{i + offset + 1}: {line}" for i, line in enumerate(selected)]
            return ToolResult(success=True, output="\n".join(numbered))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileWriteTool(Tool):
    name = "write_file"
    description = "Write content to a file. Creates the file if it doesn't exist."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to write"},
            "content": {"type": "string", "description": "Content to write to the file"},
        },
        "required": ["path", "content"],
    }

    def run(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            p = Path(path).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Written {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileEditTool(Tool):
    name = "edit_file"
    description = "Edit a file by replacing old text with new text. Use this for surgical edits."
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file to edit"},
            "old_text": {"type": "string", "description": "Exact text to find and replace"},
            "new_text": {"type": "string", "description": "Text to replace with"},
        },
        "required": ["path", "old_text", "new_text"],
    }

    def run(self, path: str, old_text: str, new_text: str, **kwargs) -> ToolResult:
        try:
            p = Path(path).resolve()
            if not p.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            content = p.read_text(encoding="utf-8")
            if old_text not in content:
                return ToolResult(success=False, output="", error="Old text not found in file")

            count = content.count(old_text)
            new_content = content.replace(old_text, new_text, 1)
            p.write_text(new_content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Replaced 1 of {count} occurrence(s) in {path}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
