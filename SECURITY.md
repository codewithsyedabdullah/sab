# Security Policy

SAB is self-hosted software. You are responsible for securing the infrastructure on which you run it. This document describes how vulnerabilities are reported to the maintainers and how the software is designed to be operated securely.

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.** Please report suspected security issues privately, preferably by sending a notification through the project's support/filing channels (or by contacting the maintainer directly). Provide as much detail as possible:

- The affected version or commit;
- A description of the vulnerability and its impact;
- Steps to reproduce (without exposing sensitive data);
- Any suggested remediation.

You should receive an acknowledgment. Please allow time for the issue to be assessed and addressed before public disclosure.

## Scope

The software itself — its backend (`server.py`, `sab/`) and front-end (`static/`). Issues in third-party AI providers, browsers, or the operating system are out of scope for this project.

## Security design notes

The following properties reflect the current implementation and should be preserved in changes.

### Authentication
- Passwords are hashed with **PBKDF2-HMAC-SHA256** (240,000 iterations) and a unique random salt per account; they are never stored or logged in plain text.
- Login sessions use a cryptographically random token stored in an **`HttpOnly`** cookie (`sab_session`, `SameSite=Lax`). The token is not readable by JavaScript.
- Optional **two-factor authentication (TOTP)** is supported.
- The authentication file is written with restricted permissions (`0600`).

### Data-at-rest
- Chat transcripts, memory, notes, documents, and most configuration are stored as **plain-text JSON** under `data/`. **This data is not encrypted at rest by default.**
- If you handle sensitive data, run SAB on an encrypted volume and restrict access to the server and the `data/` directory.

### Data-in-transit
- By default the server is bound to `0.0.0.0`. When serving over the network or the internet, place SAB behind TLS (for example a reverse proxy with HTTPS) so that authentication tokens and conversation content are encrypted in transit.
- No TLS/HTTPS is configured by the software itself; it is the operator's responsibility to provide it.

### Third-party AI providers
- By default SAB talks to a **local** Ollama instance. If you configure a cloud AI provider, conversation content and attachments are sent to that provider over the connection you configure. Only connect to providers you trust.

### Front-end
- Front-end assets are self-hosted (no third-party CDNs, no analytics), which avoids leaking user activity to external asset servers by default.

## Responsible operation checklist

- Run SAB on infrastructure you control and keep the OS, Python, and dependencies updated.
- Put the app behind a reverse proxy with HTTPS and strong TLS settings.
- Restrict administrative access (the first account is an administrator).
- Back up the `data/` directory and store backups securely (they contain plain-text conversations).
- When sharing an instance with others, publish an instance-specific privacy policy and enforce acceptable use.
