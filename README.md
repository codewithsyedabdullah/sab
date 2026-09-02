<div align="center">

<img src="static/icon.ico" width="100">

# SAB

### Your AI coding agent. Runs locally. Stays private.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Electron](https://img.shields.io/badge/electron-33-47848F.svg?style=for-the-badge&logo=electron&logoColor=white)](https://www.electronjs.org/)
[![GitHub release](https://img.shields.io/github/v/release/codewithsyedabdullah/sab?style=for-the-badge&color=green)](https://github.com/codewithsyedabdullah/sab/releases/latest)
[![GitHub stars](https://img.shields.io/github/stars/codewithsyedabdullah/sab?style=for-the-badge&color=yellow)](https://github.com/codewithsyedabdullah/sab)
[![GitHub issues](https://img.shields.io/github/issues/codewithsyedabdullah/sab?style=for-the-badge)](https://github.com/codewithsyedabdullah/sab/issues)

<br>

**CLI + Desktop app for AI-assisted coding.**
**Your code never leaves your machine.**

[Download](#installation) · [Quick Start](#quick-start) · [Features](#features) · [Report Bug](https://github.com/codewithsyedabdullah/sab/issues) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is SAB?

SAB is an **open-source, privacy-first coding agent** that lives on your machine. Talk to it from the **terminal** (CLI) or the **native desktop app** — your code stays local, always.

Connect it to **free local models** through Ollama, or plug in **cloud APIs** like Claude and GPT-4. Full voice input included — works completely offline.

---

## Features

<table>
<tr>
<td width="50%" valign="top">

### Core
- **CLI interface** — terminal-native, fast, no bloat
- **Desktop app** — native Electron window with system tray
- **Local LLM** — free offline coding via Ollama
- **Cloud LLM** — Claude, GPT-4, any OpenAI-compatible API
- **Voice input** — speech-to-text, fully offline

</td>
<td width="50%" valign="top">

### Tools
- **Read files** — view code with line numbers
- **Write files** — create or overwrite files
- **Edit files** — surgical find-and-replace
- **Run commands** — shell access, install packages
- **Search code** — grep and glob across your codebase

</td>
</tr>
<tr>
<td width="50%" valign="top">

### Intelligence
- **Session memory** — conversations persist across sessions
- **Streaming responses** — real-time token-by-token output
- **Multi-provider** — switch between Ollama, Claude, GPT-4
- **Model catalog** — browse and download models from HuggingFace

</td>
<td width="50%" valign="top">

### Desktop App
- **Embedded Python** — no system Python required
- **Offline STT** — voice input works without internet
- **System tray** — runs in background, stays out of your way
- **Auto-updates** — download new releases from GitHub
- **Multi-user auth** — password-hashed accounts

</td>
</tr>
</table>

---

## Installation

### Desktop App (Recommended)

Download the installer, run it, and start coding. Everything is bundled — Python runtime, STT engine, Whisper model. No internet required after install.

<div align="center">

| | Installer | Size | Description |
|---|-----------|------|-------------|
| ⬇️ | [**SAB-Setup-1.0.0.exe**](https://github.com/codewithsyedabdullah/sab/releases/latest/download/SAB-Setup-1.0.0.exe) | **276 MB** | Full installer with Start Menu shortcuts |
| ⬇️ | [**SAB-Portable-1.0.0.exe**](https://github.com/codetworksyedabdullah/sab/releases/latest/download/SAB-Portable-1.0.0.exe) | **276 MB** | Portable — run from anywhere |

</div>

### From Source (CLI)

```bash
git clone https://github.com/codewithsyedabdullah/sab.git
cd sab
pip install -e .
```

Requires **Python 3.10+** and [Ollama](https://ollama.ai) (for local models) or a cloud API key.

---

## Quick Start

### Option 1: Local models (free, offline)

```bash
# 1. Install Ollama — https://ollama.ai

# 2. Pull a coding model
ollama pull codellama:13b

# 3. Launch SAB
sab chat
```

### Option 2: Cloud models

```bash
sab chat --provider anthropic --model claude-sonnet-4-20250514 --api-key sk-xxx
sab chat --provider openai --model gpt-4o --api-key sk-xxx
```

### Option 3: Desktop app

Download the [installer](#installation), run it, and open SAB from your Start Menu.

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

| Model | Size | Best For |
|-------|------|----------|
| `codellama:13b` | 7.4 GB | Code generation (recommended) |
| `codellama:34b` | 19 GB | Complex tasks, larger context |
| `deepseek-coder:6.7b` | 3.8 GB | Lightweight, fast coding |
| `qwen2.5-coder:7b` | 4.4 GB | Strong general coding |

### Cloud (API) — Paid

| Model | Provider | Notes |
|-------|----------|-------|
| `claude-sonnet-4-20250514` | Anthropic | Best overall |
| `gpt-4o` | OpenAI | Fast, capable |
| `claude-haiku-3.5` | Anthropic | Fast, cheap |

---

## Architecture

```
sab/
├── sab/                  # Core Python package
│   ├── agent.py          # AI agent logic
│   ├── llm.py            # LLM provider abstraction
│   ├── config.py         # Configuration management
│   └── file_tools.py     # File operation tools
├── server.py             # API server (desktop app backend)
├── static/               # Desktop app frontend
├── desktop/              # Electron wrapper
│   ├── electron/         # Main process + preload
│   ├── runtime/          # Embedded Python (build-time)
│   └── prepare-runtime.ps1
├── offline/              # Offline wheels + Whisper model seed
├── CONTRIBUTING.md       # Contributor guidelines
├── PRIVACY.md            # Privacy policy
├── SECURITY.md           # Security practices
└── LICENSE               # MIT License
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| CLI | Python 3.10+ · Typer · Rich |
| Agent | LiteLLM (multi-provider LLM) |
| Server | FastAPI · Uvicorn · WebSockets |
| STT | faster-whisper (offline) · Cloud fallback |
| Desktop | Electron 33 · electron-builder |
| Auth | PBKDF2-SHA256 password hashing |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/sab.git

# 2. Create a branch
git checkout -b feature/amazing-feature

# 3. Make changes and commit
git commit -m "feat: add amazing feature"

# 4. Push and open a PR
git push origin feature/amazing-feature
```

---

## License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<div align="center">

### Legal

[Privacy](PRIVACY.md) · [Terms](TERMS.md) · [Security](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Notices](NOTICE.md)

---

**Built with care by [Syed Abdullah Yaqoob](https://github.com/codewithsyedabdullah)**

</div>
