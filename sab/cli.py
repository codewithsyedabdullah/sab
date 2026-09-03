from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme

from .agent import Agent
from .config import Config

app = typer.Typer(
    name="sab",
    help="SAB - Open-source coding agent that works locally.",
    no_args_is_help=True,
)
console = Console(theme=Theme({
    "info": "cyan",
    "success": "green",
    "error": "red bold",
    "tool": "yellow",
    "user": "blue",
}))


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]SAB[/bold cyan] v0.1.0\n[dim]Open-source coding agent[/dim]\n[dim]Type 'exit' to quit, 'reset' to clear history[/dim]",
        border_style="cyan",
    ))


def handle_thinking(text: str):
    console.print(f"[dim]{text}[/dim]")


def handle_tool(name: str, args: dict):
    args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
    console.print(f"[tool]  -> {name}({args_str})[/tool]")


@app.command()
def chat(
    model: str = typer.Option("qwen2.5:0.5b", "--model", "-m", help="LLM model name"),
    provider: str = typer.Option("ollama", "--provider", "-p", help="LLM provider (ollama/anthropic/openai)"),
    workspace: str = typer.Option(".", "--workspace", "-w", help="Working directory"),
    api_key: str = typer.Option("", "--api-key", help="API key (for anthropic/openai)"),
    max_iterations: int = typer.Option(50, "--max-iter", help="Max tool call iterations"),
):
    """Start an interactive coding session."""
    print_banner()

    config = Config.from_env()
    config.llm.model = model
    config.llm.provider = provider
    config.workspace = Path(workspace).resolve()
    config.agent.max_iterations = max_iterations
    if api_key:
        config.llm.api_key = api_key

    os.chdir(config.workspace)
    agent = Agent(config)

    console.print(f"[info]Model: {config.llm.model} | Provider: {config.llm.provider} | Workspace: {config.workspace}[/info]\n")

    while True:
        try:
            user_input = Prompt.ask("[user]You[/user]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]Bye![/info]")
            break

        if user_input.strip().lower() in ("exit", "quit", "q"):
            console.print("[info]Bye![/info]")
            break

        if user_input.strip().lower() == "reset":
            agent.reset()
            console.print("[info]History cleared.[/info]")
            continue

        if not user_input.strip():
            continue

        with console.status("[bold cyan]Thinking...[/bold cyan]"):
            response = agent.run(user_input, on_thinking=handle_thinking, on_tool=handle_tool)

        console.print()
        console.print(Markdown(response))
        console.print()


@app.command()
def run(
    prompt: str = typer.Argument(..., help="The task to execute"),
    model: str = typer.Option("qwen2.5:0.5b", "--model", "-m"),
    provider: str = typer.Option("ollama", "--provider", "-p"),
    workspace: str = typer.Option(".", "--workspace", "-w"),
    api_key: str = typer.Option("", "--api-key"),
):
    """Run a single task and exit."""
    config = Config.from_env()
    config.llm.model = model
    config.llm.provider = provider
    config.workspace = Path(workspace).resolve()
    if api_key:
        config.llm.api_key = api_key

    os.chdir(config.workspace)
    agent = Agent(config)

    console.print(f"[tool]Running: {prompt}[/tool]")
    with console.status("[bold cyan]Working...[/bold cyan]"):
        response = agent.run(prompt, on_tool=handle_tool)

    console.print()
    console.print(Markdown(response))


@app.command()
def models():
    """List recommended models."""
    console.print(Panel.fit(
        "[bold]Recommended Models[/bold]\n\n"
        "[bold cyan]Local (Ollama):[/bold cyan]\n"
        "  codellama:13b       - Best for code (recommended)\n"
        "  codellama:34b       - Larger, more capable\n"
        "  llama3.1:8b         - Fast, general purpose\n"
        "  deepseek-coder:6.7b - Great for code, lightweight\n"
        "  qwen2.5-coder:7b    - Strong code model\n\n"
        "[bold cyan]API (cloud):[/bold cyan]\n"
        "  claude-sonnet-4-20250514  - Best overall (Anthropic)\n"
        "  gpt-4o               - Fast, capable (OpenAI)\n"
        "  claude-haiku-3.5     - Fast, cheap (Anthropic)",
        border_style="cyan",
    ))


if __name__ == "__main__":
    app()
