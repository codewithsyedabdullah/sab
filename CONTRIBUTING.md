# Contributing to SAB

Thank you for your interest in contributing to SAB. This project is a self-hosted AI chat and coding agent written primarily in Python (backend) with static HTML/CSS/JavaScript (front-end). Please review the guidance below before opening issues or submitting changes.

## Code of Conduct

By participating, you agree to behave respectfully and constructively. Harassment, discrimination, and personal attacks are not tolerated in any channel.

## Getting started

1. Fork the repository and create a feature branch.
2. Install the project in editable mode and pull a local model (Ollama) to test locally:

   ```bash
   pip install -e .
   ollama pull qwen2.5:0.5b   # or any model you prefer
   ```

3. Run the web server and open `http://localhost:3000`:

   ```bash
   sab web   # or: python server.py
   ```

## Project layout

- `server.py` — FastAPI web server (routes, storage, auth, LLM proxying).
- `sab/` — core library (agent, LLM client, config, CLI).
- `static/` — browser front-end (HTML, CSS, vendored JS modules, fonts).
- `data/` — runtime data created on disk (chats, memory, uploads, settings). Do not commit this.

## Development workflow

- Run tests and lint before submitting:

  ```bash
  python -m pytest
  ruff check .
  ```

- Keep changes focused and atomic. Each pull request should address one concern.
- Add or update tests for backend changes. Front-end changes should be manually verified in a browser.
- Do not commit secrets, API keys, or files under `data/`.
- Keep all UI text and feature names consistent with the current naming conventions (e.g. "Memory", "Recipes", "Research", "Documents", "Model Arena").

## Commit style

Use concise, prefixed commit messages that match the repo's existing style, for example: `feat:`, `fix:`, `ui:`. Include a short description of the change.

## Submitting a pull request

1. Run `ruff check .` and `python -m pytest` locally and confirm they pass.
2. Push your branch and open a pull request against `main`.
3. Describe the change, the motivation, and how to verify it. Reference any related issue.

## Reporting issues

Before opening an issue, search to see if it has already been reported. Include:

- The version/commit you are running;
- Steps to reproduce;
- Expected vs. actual behavior;
- Any relevant logs or screenshots.

## Licensing

By contributing, you agree that your contributions are licensed under the MIT License used by this project (see `LICENSE`).
