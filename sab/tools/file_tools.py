from __future__ import annotations

import os
import re
import subprocess
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import Config

DANGEROUS_COMMANDS = {"rm -rf /", "mkfs", "dd if=", ":(){", "fork", "shutdown", "reboot", "halt", "init 0", "init 6"}

BLOCKED_PATTERNS = [
    r"etc/passwd",
    r"etc/shadow",
    r"\.ssh/",
    r"\.env\b",
    r"secret",
    r"password",
    r"token",
    r"api[_-]?key",
]


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    _fn: Any = field(default=None, repr=False)

    def run(self, **kwargs) -> ToolResult:
        return self._fn(**kwargs)

    def to_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _check_safety(command: str) -> str | None:
    cmd_lower = command.lower()
    for danger in DANGEROUS_COMMANDS:
        if danger in cmd_lower:
            return f"Blocked: command contains dangerous pattern '{danger}'"
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd_lower):
            return f"Blocked: command may expose sensitive data (matched: {pattern})"
    return None


def _read_file(file_path: str, offset: int = 1, limit: int = 2000) -> ToolResult:
    try:
        p = Path(file_path)
        if not p.exists():
            return ToolResult(False, "", f"File not found: {file_path}")
        if p.stat().st_size > 1_000_000:
            return ToolResult(False, "", f"File too large ({p.stat().st_size} bytes). Read with offset/limit.")
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, offset - 1)
        end = start + limit
        numbered = [f"{i + 1}: {line}" for i, line in enumerate(lines[start:end], start=start)]
        return ToolResult(True, "\n".join(numbered))
    except Exception as e:
        return ToolResult(False, "", str(e))


def _write_file(file_path: str, content: str) -> ToolResult:
    try:
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return ToolResult(True, f"Wrote {len(content)} bytes to {file_path}")
    except Exception as e:
        return ToolResult(False, "", str(e))


def _edit_file(file_path: str, old_string: str, new_string: str) -> ToolResult:
    try:
        p = Path(file_path)
        if not p.exists():
            return ToolResult(False, "", f"File not found: {file_path}")
        content = p.read_text(encoding="utf-8")
        if old_string not in content:
            return ToolResult(False, "", f"old_string not found in {file_path}")
        count = content.count(old_string)
        if count > 1:
            return ToolResult(False, "", f"Found {count} matches. Provide more context.")
        new_content = content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")
        return ToolResult(True, f"Edited {file_path} successfully")
    except Exception as e:
        return ToolResult(False, "", str(e))


def _run_shell(command: str, timeout: int = 30) -> ToolResult:
    safety = _check_safety(command)
    if safety:
        return ToolResult(False, "", safety)
    try:
        is_windows = os.name == "nt"
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(Config.from_env().workspace),
            **({"encoding": "utf-8", "errors": "replace"} if not is_windows else {}),
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}" if output else result.stderr
        if len(output) > 10000:
            output = output[:10000] + "\n... (truncated)"
        if result.returncode != 0:
            return ToolResult(False, output or "Command failed (no output)", f"Exit code: {result.returncode}")
        return ToolResult(True, output or "Command completed (no output)")
    except subprocess.TimeoutExpired:
        return ToolResult(False, "", f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(False, "", str(e))


def _grep(pattern: str, path: str = ".", include: str = "") -> ToolResult:
    try:
        rg_cmd = ["rg", "-n", "--no-heading"]
        if include:
            rg_cmd.extend(["--glob", include])
        rg_cmd.extend([pattern, path])
        result = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout
        if len(output) > 10000:
            lines = output.splitlines()
            output = "\n".join(lines[:200]) + f"\n... ({len(lines)} total matches, truncated)"
        return ToolResult(True, output or "No matches found")
    except FileNotFoundError:
        cmd = f'find . -name "{include}" -exec grep -Hn "{pattern}" {{}} \\;' if include else f'grep -rHn "{pattern}" .'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return ToolResult(True, result.stdout or "No matches found (grep fallback)")
    except Exception as e:
        return ToolResult(False, "", str(e))


def _glob(pattern: str, path: str = ".") -> ToolResult:
    try:
        matches = sorted(Path(path).glob(pattern))
        if not matches:
            matches = sorted(Path(path).rglob(pattern))
        output = "\n".join(str(m) for m in matches[:200])
        return ToolResult(True, output or "No files found")
    except Exception as e:
        return ToolResult(False, "", str(e))


ALL_TOOLS = [
    Tool(
        name="read_file",
        description="Read a file's contents. Use offset and limit for large files.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "integer", "description": "Starting line number (1-indexed, default: 1)"},
                "limit": {"type": "integer", "description": "Max lines to read (default: 2000)"},
            },
            "required": ["file_path"],
        },
        _fn=_read_file,
    ),
    Tool(
        name="write_file",
        description="Create or overwrite a file with new content.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["file_path", "content"],
        },
        _fn=_write_file,
    ),
    Tool(
        name="edit_file",
        description="Edit a file by replacing exact text. The old_string must match exactly (including whitespace).",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the file"},
                "old_string": {"type": "string", "description": "Exact text to find and replace"},
                "new_string": {"type": "string", "description": "Replacement text"},
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        _fn=_edit_file,
    ),
    Tool(
        name="run_shell",
        description="Execute a shell command. Returns stdout/stderr. Use for running code, installing packages, git commands.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
            },
            "required": ["command"],
        },
        _fn=_run_shell,
    ),
    Tool(
        name="grep",
        description="Search file contents with regex. Returns matching lines with file paths and line numbers.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search in (default: .)"},
                "include": {"type": "string", "description": "File pattern filter (e.g. '*.py')"},
            },
            "required": ["pattern"],
        },
        _fn=_grep,
    ),
    Tool(
        name="glob",
        description="Find files by name pattern. Supports * and ** for recursive matching.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py', 'src/**/*.ts')"},
                "path": {"type": "string", "description": "Directory to search in (default: .)"},
            },
            "required": ["pattern"],
        },
        _fn=_glob,
    ),
]
