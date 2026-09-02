<div align="center">

# SAB

### Open-source AI coding agent that runs on your machine.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
[![GitHub stars](https://img.shields.io/github/stars/codewithsyedabdullah/sab?style=social)](https://github.com/codewithsyedabdullah/sab)

**Your code never leaves your machine.**

[Download for Windows](#installation) · [Quick Start](#quick-start) · [Report Bug](https://github.com/codewithsyedabdullah/sab/issues) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is SAB?

SAB is a **self-hosted, open-source AI coding assistant** that works locally on your machine. It has a CLI for terminal power users, a web UI for browser-based chat, and a native desktop app — all connected to the same server.

Use **free local models** via Ollama, or connect to **cloud APIs** like Claude and GPT-4. Your code, your machine, your choice.

---

## Features

| | Feature | Description |
|---|---|---|
| 🔒 | **Privacy-first** | All code stays on your machine. No cloud uploads. |
| 🖥️ | **CLI + Web + Desktop** | Three interfaces — terminal, browser, or native desktop app. |
| 🤖 | **Local LLM** | Free offline coding with Ollama (CodeLlama, DeepSeek, Qwen). |
| ☁️ | **Cloud LLM** | Claude, GPT-4, and any OpenAI-compatible API. |
| 🎙️ | **Voice input** | Speech-to-text built in — works fully offline. |
| 📝 | **File tools** | Read, write, and edit files with surgical precision. |
| ⚡ | **Shell access** | Run commands, install packages, execute code. |
| 🔍 | **Code search** | Grep and glob across your entire codebase. |
| 🧠 | **Session memory** | Conversations persist across sessions. |
| 📡 | **Real-time streaming** | Token-by-token responses as they're generated. |
| 👥 | **Multi-user auth** | Password-hashed accounts with per-user sessions. |
| 🎨 | **Themes** | Customizable light/dark themes. |

---

## Installation

### Desktop App (Recommended)

Download the installer and run it — everything is included.

| Installer | Size | Description |
|-----------|------|-------------|
| [**SAB-Setup-1.0.0.exe**](https://github.com/codewithsyedabdullah/sab/releases/latest/download/SAB-Setup-1.0.0.exe) | ~276 MB | Full NSIS installer with Start Menu shortcuts |
| [**SAB-Portable-1.0.0.exe**](https://github.com/codewithsyedabdullah/sab/releases/latest/download/SAB-Portable-1.0.0.exe) | ~256 MB | Portable — run from anywhere, no install needed |

> **What's included:** Python runtime, faster-whisper STT, Whisper base model (141 MB) — fully offline, no internet required after install.

### pip (CLI + Web UI)

```bash
# Install from source
git clone https://github.com/codewithsyedabdullah/sab.git
cd sab
pip install -e .
```

### Requirements (pip install)

- Python 3.10+
- [Ollama](https://ollama.ai) for local models (or a cloud API key)

---

## Quick Start

### 1. Start a local model (free, offline)

```bash
# Install Ollama
# https://ollama.ai

# Pull a coding model
ollama pull codellama:13b
```

### 2. Launch SAB

```bash
# Web UI (recommended)
sab web

# CLI
sab chat
```

Open **http://localhost:3000** in your browser.

### 3. Or use a cloud model

```bash
sab chat --provider anthropic --model claude-sonnet-4-20250514 --api-key sk-xxx
sab chat --provider openai --model gpt-4o --api-key sk-xxx
```

---

## Configuration

Create a `.env` file in the project root:

```env
SAB_PROVIDER=ollama
SAB_MODEL=codellama:13b
SAB_API_KEY=
SAB_WORKSPACE=.
```

Or use CLI flags:

```bash
sab chat --provider openai --model gpt-4o --api-key sk-xxx
```

---

## Recommended Models

### Local (Ollama) — Free

| Model | Size | Notes |
|-------|------|-------|
| `codellama:13b` | 7.4 GB | Best for code (recommended) |
| `codellama:34b` | 19 GB | Larger, more capable |
| `deepseek-coder:6.7b` | 3.8 GB | Great for code, lightweight |
| `qwen2.5-coder:7b` | 4.4 GB | Strong code model |

### Cloud (API) — Paid

| Model | Provider | Notes |
|-------|----------|-------|
| `claude-sonnet-4-20250514` | Anthropic | Best overall |
| `gpt-4o` | OpenAI | Fast, capable |
| `claude-haiku-3.5` | Anthropic | Fast, cheap |

---

## Tools

SAB has access to these tools during conversations:

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents with line numbers |
| `write_file` | Create or overwrite a file |
| `edit_file` | Surgical find-and-replace in a file |
| `run_shell` | Execute shell commands |
| `grep` | Search code with regex |
| `glob` | Find files by pattern |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| CLI | Python 3.10+ · Typer · Rich |
| Server | FastAPI · Uvicorn · WebSockets |
| LLM | LiteLLM (multi-provider) |
| STT | faster-whisper (offline) · Cloud fallback |
| Desktop | Electron 33 · electron-builder |
| Frontend | Vanilla JS · HTML/CSS |

---

## Project Structure

```
sab/
├── sab/                # Core Python package (agent, LLM, tools)
├── server.py           # FastAPI server
├── static/             # Web UI (HTML/CSS/JS)
├── desktop/            # Electron desktop app
│   ├── electron/       # Main process
│   ├── runtime/        # Embedded Python (build-time)
│   └── prepare-runtime.ps1
├── offline/            # Offline wheels + model seed
└── tests/              # Test suite
```

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

SAB is open-source software distributed under the **MIT License**. See [LICENSE](LICENSE) for the full text.

---

## Legal

- [PRIVACY](PRIVACY.md) — How SAB stores and processes your data.
- [TERMS](TERMS.md) — Terms of service.
- [NOTICE](NOTICE.md) — Third-party attributions.
- [CONTRIBUTING](CONTRIBUTING.md) — Contributor guidelines.
- [SECURITY](SECURITY.md) — Vulnerability reporting and security practices.
