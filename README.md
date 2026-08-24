# SAB

Open-source coding agent that works locally. Your code stays on your machine.

## Features

- **CLI interface** - Terminal-based, fast, no bloat
- **Local LLM support** - Runs on Ollama (CodeLlama, DeepSeek, Qwen)
- **Cloud LLM support** - Claude, GPT-4 via API
- **File tools** - Read, write, edit files
- **Shell access** - Run commands, install packages, execute code
- **Code search** - Grep and glob across your codebase
- **Safe by default** - Blocked dangerous commands, file size limits

## Quick Start

### Install

```bash
pip install -e .
```

### Setup Ollama (local, free)

```bash
# Install Ollama: https://ollama.ai
ollama pull codellama:13b
```

### Run

```bash
# Interactive chat
sab chat

# Single task
sab run "add error handling to main.py"

# Use Claude instead
sab chat --provider anthropic --model claude-sonnet-4-20250514 --api-key sk-xxx
```

## Configuration

Create a `.env` file:

```
SAB_PROVIDER=ollama
SAB_MODEL=codellama:13b
SAB_API_KEY=
SAB_WORKSPACE=.
```

Or use CLI flags:

```bash
sab chat --provider openai --model gpt-4o --api-key sk-xxx
```

## Tools

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with line numbers |
| `write_file` | Create or overwrite a file |
| `edit_file` | Surgical find-and-replace in a file |
| `run_shell` | Execute shell commands |
| `grep` | Search code with regex |
| `glob` | Find files by pattern |

## Tech Stack

- Python 3.10+
- LiteLLM (multi-provider LLM support)
- Typer (CLI framework)
- Rich (terminal formatting)

## License

MIT
