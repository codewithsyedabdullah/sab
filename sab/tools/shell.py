from __future__ import annotations

import subprocess
import sys

from .base import Tool, ToolResult


class ShellTool(Tool):
    name = "run_shell"
    description = "Run a shell command. Use this to execute code, install packages, run tests, etc."
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
        },
        "required": ["command"],
    }

    BLOCKED = ["rm -rf /", "format", "del /s /q", "shutdown", "reboot"]

    def run(self, command: str, timeout: int = 30, **kwargs) -> ToolResult:
        for blocked in self.BLOCKED:
            if blocked in command.lower():
                return ToolResult(
                    success=False, output="", error=f"Blocked dangerous command: {blocked}"
                )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]\n{result.stderr}"
            if len(output) > 10000:
                output = output[:5000] + "\n... (truncated) ...\n" + output[-5000:]

            return ToolResult(
                success=result.returncode == 0,
                output=output.strip() or "(no output)",
                error="" if result.returncode == 0 else f"Exit code: {result.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
