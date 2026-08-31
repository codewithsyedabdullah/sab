# SAB Privacy Policy

**Last updated:** August 31, 2026

This Privacy Policy explains how **SAB** ("the app", "we") collects, uses, stores, and shares information when you use the application. SAB is a self-hosted artificial-intelligence chat application. Because it is designed to be run on hardware you control, most of your data never leaves your own server.

By installing, configuring, or using SAB, you agree to the practices described in this policy. If you do not agree, please do not use the app.

---

## 1. Who runs the app

SAB is self-hosted software. **You** (or your organization) are the operator of the server that runs SAB, and you control where it is installed, how it is configured, and who has access to it. Because of this, the "data controller" for the information stored in your SAB instance is the operator of that instance.

This policy describes the default behavior of the software itself. Where the app allows configuration changes (for example, connecting an external AI provider), those choices determine how your data is handled, and the responsibility for those choices rests with the operator.

---

## 2. What data the app collects and stores

SAB stores data as plain-text JSON files on the server where it runs, inside a `data/` directory. The following categories of information are stored, and all of them persist on your server's disk:

### 2.1 Account and login data
- Usernames and account records.
- **Passwords** are not stored in plain text. They are hashed using **PBKDF2-HMAC-SHA256** with 240,000 iterations and a random, per-user 16-byte salt. The stored record contains only the algorithm name, iteration count, salt, and hash — not the password itself.
- **Session tokens** used to keep you logged in, and (if enabled) optional **two-factor authentication (TOTP) settings and backup codes**.

### 2.2 Conversation content
- **Full chat transcripts**: every user message and assistant reply, including any content you type or it generates, is stored on the server so your conversations persist between visits.

### 2.3 Long-term memory and personalization
- **Memory facts** that the app stores to remember across conversations.
- **Model / provider selections**, preferences, UI settings, presets, and feature toggles.

### 2.4 Files you upload or attach
- Files you attach to chats (images, audio, documents) are stored on the server.
- If you use an external AI provider (see Section 4), attachments may be processed for vision (image description), audio transcription, or text extraction before being sent to that provider.
- Stored gallery images, calendar events, notes, tasks, documents/personal knowledge base, contacts, and email-related configuration files.

### 2.5 Integration and configuration data
- Stored **AI provider endpoints and the API keys you provide** for them (see Section 4).
- Webhook, integration, and MCP (model-context-protocol) server configuration.
- API access tokens you generate for external integrations.

---

## 3. Authentication and security

- **Passwords** are hashed with **PBKDF2-HMAC-SHA256** (240,000 iterations) with a unique random salt per account, and verified using constant-time comparison.
- **Login sessions** use a cryptographically random session token stored in an **`HttpOnly` cookie** named `sab_session` (with `SameSite=Lax`). The session token is not readable by JavaScript, which reduces the risk of theft via cross-site scripting.
- Session tokens expire after **8 hours** by default, or after **30 days** if you select "Remember me."
- You can enable optional **two-factor authentication (TOTP)** for additional account protection.
- On the server, the authentication file is written with restricted file permissions (`0600`).

*Note on storage format:* chat transcripts, memories, notes, documents, and most configuration are stored as **plain-text JSON** on the server disk. This means anyone with direct access to the server's file system or the `data/` directory can read this content. The data is **not encrypted at rest** by default. If you require encryption at rest, you should store the `data/` directory on an encrypted volume.

---

## 4. How your data is processed by AI providers

SAB is designed as a **bring-your-own-key / bring-your-own-endpoint** application.

- **By default, all local.** In its default configuration, SAB connects to a **local** AI model server (Ollama) running on the same machine (`localhost`). When no cloud endpoint is configured, your chat messages and content are processed locally and **do not leave your server**.
- **If you add a cloud provider**, you are choosing to send data to a third party. When you configure an external endpoint (for example Anthropic, OpenAI, Google Gemini, Groq, OpenRouter, DeepSeek, Mistral, Together, Fireworks, xAI Grok, NVIDIA, or any custom URL), then:
  - Your **conversation content** (user messages and assistant replies) is sent to that provider's server via the URL you configured, in order to generate responses.
  - **Attachments** may be sent to that provider for image description, audio transcription, or text extraction.
  - The provider processes this data according to **that provider's own privacy policy and terms**, over which SAB has no control.
  - Provider **API keys** you enter are used to authenticate those requests and are stored by SAB (Section 2.5).

This means **the privacy of your conversations depends on which AI provider you connect to and where you run SAB**. If you require strict confidentiality, use a local model and do not configure any external provider.

---

## 5. Analytics, tracking, and third-party content

- **SAB does not include analytics, advertising, tracking pixels, or telemetry.** No analytics SDKs or tracking scripts are bundled with the app.
- **Front-end assets are self-hosted.** Static scripts, styles, and fonts (including code highlighting, math rendering, diagram rendering, and fonts) are served from your own SAB server, not from third-party CDNs. Visiting the SAB interface does not "phone home" to external asset servers.
- **One conditional exception:** the optional in-browser **Python code runner** (used to execute Python notebooks/code in the editor) loads the **Pyodide** runtime from *jsdelivr.net* at runtime, on first use. This request only happens if you actually run Python code through that feature; it does not run on ordinary page loads. If you prefer, you can self-host Pyodide or disable that feature. Nothing else in the app fetches third-party resources.
- The app does not voluntarily transmit usage statistics, diagnostics, or personal data to the makers of SAB.

---

## 6. Cookies and client-side storage

- **Cookies:** SAB sets a single functional cookie, `sab_session`, which holds your login session token (see Section 3). It is cleared when you log out. No tracking or cross-site cookies are set.
- **Browser storage:** The app uses your browser's `localStorage` and `sessionStorage` to remember preferences and state, including: the last username used (only if you select "Remember me"), theme, sidebar settings, current session, model selections, and a client-side copy of model-endpoint configuration. **Your main login session token is not stored in localStorage** — it is kept in the `HttpOnly` cookie.

---

## 7. How you can control, export, and delete your data

SAB provides tools for you to manage your data:

- **Delete a conversation** (session) or individual messages.
- **Compact or truncate** conversation history.
- **Delete memory facts, notes, or tasks.**
- **Delete uploaded files** and gallery items.
- **Wipe entire categories** of data (chats, memory, skills, notes, tasks, documents, gallery, calendar) including uploaded files, through the administrator "Danger Zone" tools.
- **Export your data** (sessions, notes, tasks) for portability.
- **Log out** to revoke your current session.
- Administrators can **delete user accounts**.

To permanently remove data, follow the deletion steps in the app's interface, or remove the relevant files from the server's `data/` directory and its backups. Because chat transcripts and memories are stored as plain-text files, deleting them from the app removes them from normal operation; however, if you keep server backups, copies may persist in those backups until they are also removed.

---

## 8. Data retention

SAB does not automatically delete your content on a schedule. Conversation transcripts, memories, notes, documents, and uploaded files are retained **until you delete them** (or until the server's storage is cleared). Account records and authentication data are retained until the account is deleted.

---

## 9. Children's privacy

SAB is not directed to children, and it does not knowingly collect information from children. If you believe a child has used SAB in a way that stored personal data on a server you control, delete that data using the tools described in Section 7.

---

## 10. Changes to this policy

We may update this Privacy Policy from time to time to reflect changes in the software or for legal reasons. The "Last updated" date at the top of this page indicates when it was last revised. If you run SAB, please review this policy periodically.

---

## 11. Contact

Because SAB is self-hosted, the person or organization best able to answer questions about the data stored on a particular instance is the **operator of that instance** (you or your host). For questions about the app itself, you can reach its maintainers through the project's support channels.

---

## Summary

- **Where your data lives:** on the server you run, in plain-text JSON files under `data/`.
- **Passwords:** hashed with PBKDF2-HMAC-SHA256 (240k iterations + salt); never stored in plain text.
- **AI processing:** local by default; **you choose** whether to connect a cloud AI provider, at which point conversation content and attachments are sent to that provider.
- **No analytics / no third-party CDNs / no tracking.**
- **You keep control:** delete, wipe, and export tools are built in.
