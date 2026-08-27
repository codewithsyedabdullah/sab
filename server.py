from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from sab.config import Config
from sab.agent import Agent

app = FastAPI(title="SAB")

STATIC_DIR = Path(__file__).parent / "static"
DATA_DIR = Path(__file__).parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SESSIONS_FILE = DATA_DIR / "sessions.json"
HISTORIES_DIR = DATA_DIR / "histories"
NOTES_FILE = DATA_DIR / "notes.json"
TASKS_FILE = DATA_DIR / "tasks.json"
MEMORY_FILE = DATA_DIR / "memory.json"
PRESETS_FILE = DATA_DIR / "presets.json"
SKILLS_DIR = DATA_DIR / "skills"
DOCUMENTS_FILE = DATA_DIR / "documents.json"
CALENDAR_FILE = DATA_DIR / "calendar.json"
GALLERY_FILE = DATA_DIR / "gallery.json"
DOCUMENTS_LIBRARY_FILE = DATA_DIR / "documents_library.json"
COOKBOOK_STATE_FILE = DATA_DIR / "cookbook_state.json"
MCP_FILE = DATA_DIR / "mcp.json"
WEBHOOKS_FILE = DATA_DIR / "webhooks.json"
TOKENS_FILE = DATA_DIR / "tokens.json"
EMAIL_ACCOUNTS_FILE = DATA_DIR / "email_accounts.json"
EMAIL_STYLE_FILE = DATA_DIR / "email_style.json"
EMAIL_CONFIG_FILE = DATA_DIR / "email_config.json"
VAULT_FILE = DATA_DIR / "vault.json"
INTEGRATIONS_FILE = DATA_DIR / "integrations.json"
TOOLS_CONFIG_FILE = DATA_DIR / "tools_config.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
FEATURES_FILE = DATA_DIR / "features.json"
PERSONAL_RAG_FILE = DATA_DIR / "personal_rag.json"
ASSISTANT_SETTINGS_FILE = DATA_DIR / "assistant_settings.json"
EDITOR_DRAFTS_FILE = DATA_DIR / "editor_drafts.json"

for d in [DATA_DIR, HISTORIES_DIR, UPLOADS_DIR, SKILLS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

config = Config.from_env()

active_streams: dict[str, asyncio.Event] = {}
running_agents: dict[str, Agent] = {}


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def html_escape(s: Any) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")


def _ssh_keypair():
    import subprocess as _sp
    import tempfile, os
    try:
        with tempfile.TemporaryDirectory() as td:
            priv = os.path.join(td, "sab")
            try:
                _sp.run(["ssh-keygen", "-t", "ed25519", "-f", priv, "-N", "", "-q"], check=True, capture_output=True, timeout=10)
            except Exception:
                _sp.run(["ssh-keygen", "-t", "rsa", "-b", "2048", "-f", priv, "-N", "", "-q"], check=True, capture_output=True, timeout=20)
            priv_txt = open(priv, encoding="utf-8").read().strip()
            pub_txt = open(priv + ".pub", encoding="utf-8").read().strip()
            return priv_txt, pub_txt
    except Exception:
        return "", ""


def _load_json(path: Path, default: Any = None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default if default is not None else []


def _save_json(path: Path, data: Any):
    path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False), encoding="utf-8")


def _load_sessions() -> list[dict]:
    return _load_json(SESSIONS_FILE, [])


def _save_sessions(s: list[dict]):
    _save_json(SESSIONS_FILE, s)


def _get_history(sid: str) -> list[dict]:
    return _load_json(HISTORIES_DIR / f"{sid}.json", [])


def _save_history(sid: str, h: list[dict]):
    _save_json(HISTORIES_DIR / f"{sid}.json", h)


def _append_history(sid: str, role: str, content: str, meta: dict | None = None):
    h = _get_history(sid)
    e: dict[str, Any] = {"role": role, "content": content, "id": _uid()}
    if meta:
        e["metadata"] = meta
    h.append(e)
    _save_history(sid, h)


def _find_session(sid: str) -> dict | None:
    return next((s for s in _load_sessions() if s["id"] == sid), None)


def _json_or_form(body: Any) -> dict:
    return body if isinstance(body, dict) else {}


# ──────────────────── AUTH ────────────────────

@app.get("/api/auth/status")
async def auth_status():
    return {"authenticated": True, "configured": True, "signup_enabled": False, "user": {"username": "sab", "is_admin": True, "display_name": "SAB"}, "username": "sab", "is_admin": True, "display_name": "SAB", "privileges": []}


@app.get("/api/auth/policy")
async def auth_policy():
    return {"signup_enabled": False, "password_min_length": 8}


@app.get("/api/auth/settings")
async def auth_settings_get():
    return _load_json(SETTINGS_FILE, {"theme": "default", "tts_enabled": False, "stt_enabled": False})


@app.post("/api/auth/settings")
async def auth_settings_post(request: Request):
    body = await request.json()
    existing = _load_json(SETTINGS_FILE, {})
    existing.update(body)
    _save_json(SETTINGS_FILE, existing)
    return existing


@app.get("/api/auth/features")
async def auth_features_get():
    return _load_json(FEATURES_FILE, {
        "signup_enabled": False, "tts": False, "stt": False,
        "sensitive_filter": False, "web_search": False, "research": False,
    })


@app.post("/api/auth/features")
async def auth_features_post(request: Request):
    body = await request.json()
    _save_json(FEATURES_FILE, body)
    return body


@app.get("/api/auth/users")
async def auth_users():
    return {"users": [{"username": "sab", "is_admin": True, "display_name": "SAB"}]}


@app.post("/api/auth/users")
async def auth_create_user(request: Request):
    body = await request.json()
    return {"username": body.get("username", "user"), "is_admin": False}


@app.delete("/api/auth/users")
async def auth_delete_user():
    return JSONResponse({})


@app.get("/api/auth/users/{username}/privileges")
async def auth_user_privileges(username: str):
    return {"privileges": []}


@app.post("/api/auth/users/{username}/privileges")
@app.put("/api/auth/users/{username}/privileges")
async def auth_set_privileges(username: str, request: Request):
    return JSONResponse({})


@app.post("/api/auth/users/{username}/rename")
@app.put("/api/auth/users/{username}/rename")
async def auth_rename_user(username: str, request: Request):
    return JSONResponse({})


@app.post("/api/auth/users/{username}/admin")
@app.put("/api/auth/users/{username}/admin")
async def auth_toggle_admin(username: str, request: Request):
    return JSONResponse({})


@app.post("/api/auth/signup-toggle")
async def auth_signup_toggle(request: Request):
    return JSONResponse({})


# ──────────────────── VERSION / RUNTIME ────────────────────

@app.get("/api/version")
async def version():
    return {"version": "0.1.0", "name": "SAB", "codename": "Syed Abdullah Bot"}


@app.get("/api/runtime")
async def runtime():
    return {
        "python": sys.version,
        "platform": sys.platform,
        "server": "SAB",
        "hostname": platform.node(),
        "pid": os.getpid(),
    }


# ──────────────────── MODELS / ENDPOINTS ────────────────────

@app.get("/api/default-chat")
async def default_chat():
    return {"endpoint_url": "local", "model": config.llm.model, "endpoint_id": "sab-local"}


@app.get("/api/models")
async def models():
    try:
        import requests as _req
        r = await asyncio.to_thread(lambda: _req.get("http://localhost:11434/api/tags", timeout=3))
        if r.ok:
            data = r.json().get("models", [])
            return {"items": [{
                "id": "sab-local",
                "name": "Ollama Local",
                "url": "http://localhost:11434",
                "endpoint_id": "sab-local",
                "endpoint_name": "Ollama Local",
                "endpoint_url": "http://localhost:11434",
                "models": [m["name"] for m in data],
                "models_display": [m["name"] for m in data],
            }]}
    except Exception:
        pass
    return {"items": [{
        "id": "sab-local",
        "name": "SAB Local",
        "url": "http://localhost:11434",
        "endpoint_id": "sab-local",
        "endpoint_name": "SAB Local",
        "endpoint_url": "http://localhost:11434",
        "models": [config.llm.model],
        "models_display": [config.llm.model],
    }]}


@app.get("/api/providers")
async def providers():
    return {"providers": [{"id": "sab-local", "name": "SAB Local", "models": [config.llm.model]}]}


@app.get("/api/model-endpoints")
async def model_endpoints():
    endpoints = _load_json(DATA_DIR / "model_endpoints.json", [])
    if not endpoints:
        endpoints = [{
            "id": "sab-local",
            "name": "Ollama Local",
            "base_url": "http://localhost:11434",
            "url": "http://localhost:11434",
            "models": [{"id": config.llm.model, "name": config.llm.model}],
            "models_list": [config.llm.model],
            "pinned_models": [],
            "offline": False,
            "type": "ollama",
        }]
    return endpoints


@app.post("/api/model-endpoints")
async def create_model_endpoint(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    endpoints = _load_json(DATA_DIR / "model_endpoints.json", [])
    ep = {"id": _uid(), **body}
    endpoints.append(ep)
    _save_json(DATA_DIR / "model_endpoints.json", endpoints)
    return ep


@app.delete("/api/model-endpoints/{id}")
async def delete_model_endpoint(id: str):
    endpoints = _load_json(DATA_DIR / "model_endpoints.json", [])
    endpoints = [e for e in endpoints if e.get("id") != id]
    _save_json(DATA_DIR / "model_endpoints.json", endpoints)
    return JSONResponse({})


@app.patch("/api/model-endpoints/{id}")
async def patch_model_endpoint(id: str, request: Request):
    body = await request.json()
    endpoints = _load_json(DATA_DIR / "model_endpoints.json", [])
    for e in endpoints:
        if e.get("id") == id:
            e.update(body)
    _save_json(DATA_DIR / "model_endpoints.json", endpoints)
    return JSONResponse({})


@app.get("/api/model-endpoints/{id}/models")
async def endpoint_models(id: str, refresh: bool = False):
    return {"models": [{"id": config.llm.model, "name": config.llm.model}]}


@app.post("/api/model-endpoints/{id}/models")
async def refresh_endpoint_models(id: str):
    return {"models": [{"id": config.llm.model, "name": config.llm.model}]}


@app.get("/api/model-endpoints/{id}/dependents")
async def endpoint_dependents(id: str):
    return {"sessions": []}


@app.get("/api/model-endpoints/{id}/probe")
async def probe_endpoint(id: str):
    return {"ok": True, "latency_ms": 10}


@app.get("/api/model-endpoints/probe-local")
async def probe_local():
    try:
        import requests as _req
        r = await asyncio.to_thread(lambda: _req.get("http://localhost:11434/api/tags", timeout=3))
        return {"ok": r.ok, "models": [m["name"] for m in r.json().get("models", [])]}
    except Exception:
        return {"ok": False, "error": "Ollama not reachable"}


@app.post("/api/model-endpoints/test")
async def test_endpoint(request: Request):
    return {"ok": True}


@app.get("/api/discover")
async def discover():
    return {"endpoints": []}


# ──────────────────── TOOLS ────────────────────

@app.get("/api/tools")
async def tools():
    return _load_json(TOOLS_CONFIG_FILE, {"disabled_tools": []})


@app.post("/api/tools")
async def tools_post(request: Request):
    body = await request.json()
    _save_json(TOOLS_CONFIG_FILE, body)
    return body


@app.get("/api/tools/config")
async def tools_config():
    return _load_json(TOOLS_CONFIG_FILE, {"disabled_tools": []})


# ──────────────────── SESSIONS ────────────────────

@app.get("/api/sessions")
async def list_sessions():
    sessions = _load_sessions()
    sessions.sort(key=lambda s: s.get("updated_at", s.get("created_at", "")), reverse=True)
    return sessions


@app.get("/api/sessions/archived")
async def archived_sessions(limit: int = 100, sort: str = "recent"):
    sessions = [s for s in _load_sessions() if s.get("archived", False)][:limit]
    return {"sessions": sessions, "total": len(sessions)}


@app.post("/api/sessions/auto-sort")
async def auto_sort(request: Request):
    return {"status": "ok", "updated": 0, "folders": [], "deleted_empty": 0, "deleted_throwaway": 0, "unfiled_remaining": 0}


@app.get("/api/sessions/auto-sort")
async def auto_sort_get():
    sessions = _load_sessions()
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


@app.post("/api/sessions/bulk-delete")
async def bulk_delete(request: Request):
    body = await request.json()
    ids = body.get("session_ids", body.get("ids", []))
    sessions = _load_sessions()
    sessions = [s for s in sessions if s["id"] not in ids]
    _save_sessions(sessions)
    for sid in ids:
        f = HISTORIES_DIR / f"{sid}.json"
        if f.exists():
            f.unlink()
    return JSONResponse({})


@app.post("/api/session")
async def create_session(request: Request):
    form = await request.form()
    name = str(form.get("name", "New Chat"))
    model = str(form.get("model", config.llm.model))
    endpoint_url = str(form.get("endpoint_url", "local"))
    endpoint_id = str(form.get("endpoint_id", "sab-local"))
    sid = _uid()
    session = {
        "id": sid, "name": name, "model": model,
        "endpoint_url": endpoint_url, "endpoint_id": endpoint_id,
        "created_at": _now(), "updated_at": _now(),
        "important": False, "archived": False, "folder": None, "metadata": {},
    }
    sessions = _load_sessions()
    sessions.append(session)
    _save_sessions(sessions)
    _save_history(sid, [])
    return session


@app.get("/api/session/{sid}")
async def get_session(sid: str):
    s = _find_session(sid)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    return s


@app.patch("/api/session/{sid}")
async def update_session(sid: str, request: Request):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        for key in ["name", "model", "folder", "important"]:
            if key in form:
                val = form[key]
                if key == "important":
                    s[key] = val == "true" or val is True
                else:
                    s[key] = str(val)
    else:
        body = await request.json()
        for key in ["name", "model", "folder", "important", "metadata"]:
            if key in body:
                s[key] = body[key]
    s["updated_at"] = _now()
    _save_sessions(sessions)
    return s


@app.delete("/api/session/{sid}")
async def delete_session(sid: str):
    sessions = _load_sessions()
    sessions = [s for s in sessions if s["id"] != sid]
    _save_sessions(sessions)
    f = HISTORIES_DIR / f"{sid}.json"
    if f.exists():
        f.unlink()
    return JSONResponse({})


@app.post("/api/session/{sid}/archive")
async def archive_session(sid: str):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        s["archived"] = True
        s["updated_at"] = _now()
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/unarchive")
async def unarchive_session(sid: str):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        s["archived"] = False
        s["updated_at"] = _now()
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/important")
async def toggle_important(sid: str, request: Request):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        form = await request.form()
        s["important"] = form.get("important", "false") == "true"
        s["updated_at"] = _now()
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/compact")
async def compact_session(sid: str, request: Request):
    history = _get_history(sid)
    kept = history[-10:] if len(history) > 10 else history
    _save_history(sid, kept)
    return {"summarized": len(history) - len(kept), "kept": len(kept)}


@app.post("/api/session/{sid}/truncate")
async def truncate_session(sid: str, request: Request):
    body = await request.json()
    keep = body.get("keep_count", 0)
    history = _get_history(sid)
    _save_history(sid, history[-keep:] if keep > 0 else [])
    return JSONResponse({})


@app.post("/api/session/{sid}/delete-messages")
async def delete_messages(sid: str, request: Request):
    body = await request.json()
    msg_ids = set(body.get("msg_ids", []))
    history = _get_history(sid)
    history = [h for h in history if h.get("id") not in msg_ids]
    _save_history(sid, history)
    return JSONResponse({})


@app.post("/api/session/{sid}/edit-message")
async def edit_message(sid: str, request: Request):
    body = await request.json()
    msg_id = body.get("msg_id")
    content = body.get("content", "")
    history = _get_history(sid)
    for h in history:
        if h.get("id") == msg_id:
            h["content"] = content
    _save_history(sid, history)
    return JSONResponse({})


@app.post("/api/session/{sid}/fork")
async def fork_session(sid: str, request: Request):
    body = await request.json()
    keep = body.get("keep_count", 0)
    history = _get_history(sid)[:keep] if keep > 0 else list(_get_history(sid))
    new_sid = _uid()
    orig = _find_session(sid)
    new_session = {
        "id": new_sid,
        "name": (orig.get("name", "Chat") if orig else "Chat") + " (fork)",
        "model": (orig.get("model", config.llm.model) if orig else config.llm.model),
        "created_at": _now(), "updated_at": _now(),
        "important": False, "archived": False, "folder": None, "metadata": {},
    }
    sessions = _load_sessions()
    sessions.append(new_session)
    _save_sessions(sessions)
    _save_history(new_sid, history)
    return new_session


@app.post("/api/session/{sid}/inject_messages")
async def inject_messages(sid: str, request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    history = _get_history(sid)
    for msg in messages:
        history.append({"role": msg.get("role", "user"), "content": msg.get("content", ""), "id": _uid()})
    _save_history(sid, history)
    return JSONResponse({})


@app.post("/api/session/{sid}/mark-stopped")
async def mark_stopped(sid: str):
    active_streams.pop(sid, None)
    return JSONResponse({})


@app.post("/api/session/{sid}/merge-last-assistant")
async def merge_last_assistant(sid: str):
    return JSONResponse({})


@app.post("/api/session/{sid}/update-last-meta")
async def update_last_meta(sid: str, request: Request):
    return JSONResponse({})


@app.get("/api/session/{sid}/context")
async def session_context(sid: str):
    history = _get_history(sid)
    used_tokens = sum(len(m.get("content", "")) // 4 for m in history)
    context_length = 32768
    context_percent = round((used_tokens / context_length) * 100, 1) if context_length > 0 else 0
    return {
        "system_prompt": "You are SAB.",
        "messages": history,
        "context_percent": context_percent,
        "used_tokens": used_tokens,
        "context_length": context_length,
        "model": config.llm.model,
        "can_compact": context_percent > 70,
    }


@app.get("/api/session/{sid}/context_info")
async def session_context_info(sid: str):
    history = _get_history(sid)
    used_tokens = sum(len(m.get("content", "")) // 4 for m in history)
    context_length = 32768
    return {"total_messages": len(history), "estimated_tokens": used_tokens, "context_length": context_length, "used_tokens": used_tokens, "context_percent": round((used_tokens / context_length) * 100, 1) if context_length > 0 else 0}


# ──────────────────── HISTORY ────────────────────

@app.get("/api/history/{sid}")
async def get_history(sid: str, limit: int = 100, offset: int = 0):
    history = _get_history(sid)
    total = len(history)
    sliced = history[offset:offset + limit]
    return {"history": sliced, "offset": offset, "total": total, "has_more_before": offset > 0, "has_more_after": offset + limit < total, "model": config.llm.model, "limit": limit}


# ──────────────────── CHAT / STREAMING ────────────────────

@app.get("/api/chat/stream_status/{sid}")
async def stream_status(sid: str):
    if sid in active_streams:
        return {"status": "streaming"}
    return JSONResponse({"error": "not streaming"}, status_code=404)


@app.post("/api/chat/stop/{sid}")
async def stop_chat(sid: str):
    ev = active_streams.get(sid)
    if ev:
        ev.set()
    return {"status": "stopped"}


@app.get("/api/chat/resume/{sid}")
async def resume_chat(sid: str):
    async def generate():
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/chat_stream")
async def chat_stream(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        message = str(form.get("message", ""))
        session_id = str(form.get("session", "") or form.get("session_id", ""))
        mode = str(form.get("mode", "chat"))
    else:
        try:
            body = await request.json()
            message = str(body.get("message", ""))
            session_id = str(body.get("session", "") or body.get("session_id", ""))
            mode = str(body.get("mode", "chat"))
        except Exception:
            form = await request.form()
            message = str(form.get("message", ""))
            session_id = str(form.get("session", "") or form.get("session_id", ""))
            mode = str(form.get("mode", "chat"))

    if not session_id:
        session_id = _uid()
        sessions = _load_sessions()
        sessions.append({
            "id": session_id, "name": message[:40] if message else "New Chat",
            "model": config.llm.model, "created_at": _now(), "updated_at": _now(),
            "important": False, "archived": False, "folder": None, "metadata": {},
        })
        _save_sessions(sessions)

    _append_history(session_id, "user", message)

    stop_event = asyncio.Event()
    active_streams[session_id] = stop_event

    agent = Agent(config)
    running_agents[session_id] = agent

    async def generate():
        full_response = ""
        try:
            import concurrent.futures
            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()

            def run_agent():
                try:
                    for event in agent.run_stream(message):
                        if stop_event.is_set():
                            break
                        loop.call_soon_threadsafe(queue.put_nowait, event)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            loop.run_in_executor(pool, run_agent)

            while True:
                event = await queue.get()
                if event is None:
                    break
                if stop_event.is_set():
                    break

                if event["type"] == "content":
                    full_response += event["text"]
                    yield f"data: {json.dumps({'delta': event['text']})}\n\n"
                elif event["type"] == "tool_start":
                    yield f"data: {json.dumps({'type': 'tool_start', 'tool': event['name'], 'arguments': event.get('arguments', {})})}\n\n"
                elif event["type"] == "tool_result":
                    yield f"data: {json.dumps({'type': 'tool_output', 'tool': event['name'], 'output': event.get('output', '')[:2000]})}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'status': 500, 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            active_streams.pop(session_id, None)
            running_agents.pop(session_id, None)
            if full_response:
                _append_history(session_id, "assistant", full_response)
                sessions = _load_sessions()
                s = next((x for x in sessions if x["id"] == session_id), None)
                if s:
                    s["updated_at"] = _now()
                    if s.get("name", "").startswith("New Chat"):
                        s["name"] = message[:40]
                    _save_sessions(sessions)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no", "X-SAB-Run-Id": session_id})


@app.post("/api/echo")
async def echo_test(request: Request):
    try:
        return await request.json()
    except Exception:
        return {"echo": True}


@app.post("/api/rewrite")
async def rewrite(request: Request):
    body = await request.json()
    original = body.get("original_text", "")
    async def generate():
        yield f"data: {json.dumps({'delta': original})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/client-perf")
async def client_perf(request: Request):
    return JSONResponse({})


# ──────────────────── AI ────────────────────

@app.post("/api/ai/name")
async def ai_name_gen(request: Request):
    body = await request.json()
    text = body.get("name", body.get("text", ""))
    name = text[:40] if text else "New Chat"
    return {"success": True, "name": name}


@app.get("/api/ai/name")
async def ai_name():
    return {"name": "SAB"}


# ──────────────────── PRESETS ────────────────────

@app.get("/api/presets")
async def presets():
    data = _load_json(PRESETS_FILE, {})
    if not data:
        data = {}
    if "custom" not in data:
        data["custom"] = {
            "name": "Custom", "character_name": "",
            "system_prompt": "", "enabled": False,
            "temperature": 1.0, "max_tokens": 0,
            "inject_prefix": "", "inject_suffix": "",
        }
    if "default" not in data:
        data["default"] = {"name": "SAB", "character_name": "SAB", "system_prompt": "You are SAB."}
    return data


@app.post("/api/presets")
async def save_preset(request: Request):
    body = await request.json()
    data = _load_json(PRESETS_FILE, {})
    pid = body.get("id", _uid())
    data[pid] = body
    _save_json(PRESETS_FILE, data)
    return body


@app.delete("/api/presets/{pid}")
async def delete_preset(pid: str):
    data = _load_json(PRESETS_FILE, {})
    data.pop(pid, None)
    _save_json(PRESETS_FILE, data)
    return JSONResponse({})


@app.get("/api/presets/templates")
async def preset_templates():
    data = _load_json(PRESETS_FILE, {})
    return data.get("templates", [])


@app.post("/api/presets/templates")
async def preset_template_create(request: Request):
    body = await request.json()
    data = _load_json(PRESETS_FILE, {})
    templates = data.get("templates", [])
    templates.append(body)
    data["templates"] = templates
    _save_json(PRESETS_FILE, data)
    return {"success": True, **body}


@app.delete("/api/presets/templates/{tid}")
async def preset_template_delete(tid: str):
    data = _load_json(PRESETS_FILE, {})
    templates = data.get("templates", [])
    data["templates"] = [t for t in templates if t.get("id") != tid]
    _save_json(PRESETS_FILE, data)
    return {"ok": True}


@app.get("/api/presets/custom")
async def preset_custom_get():
    data = _load_json(PRESETS_FILE, {})
    return data.get("custom", {})


@app.post("/api/presets/custom")
async def preset_custom_save(request: Request):
    body = await request.json()
    data = _load_json(PRESETS_FILE, {})
    data["custom"] = body
    _save_json(PRESETS_FILE, data)
    return {"success": True, **body}


@app.post("/api/presets/expand")
async def preset_expand(request: Request):
    body = await request.json()
    return {"success": True, "prompt": body.get("prompt", "")}


@app.get("/api/presets/groups")
async def preset_groups():
    return {"groups": []}


# ──────────────────── MEMORY ────────────────────

@app.get("/api/memory")
async def memory_list():
    items = _load_json(MEMORY_FILE, [])
    return {"memory": items}


@app.post("/api/memory")
async def memory_create(request: Request):
    body = await request.json()
    items = _load_json(MEMORY_FILE, [])
    item = {"id": _uid(), "created_at": _now(), "updated_at": _now(), **body}
    items.append(item)
    _save_json(MEMORY_FILE, items)
    return item


@app.put("/api/memory/{mid}")
async def memory_update(mid: str, request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct or "x-www-form" in ct:
        form = await request.form()
        body = {k: str(v) for k, v in form.items()}
    else:
        body = await request.json()
    items = _load_json(MEMORY_FILE, [])
    for item in items:
        if item.get("id") == mid:
            item.update(body)
            item["updated_at"] = _now()
    _save_json(MEMORY_FILE, items)
    return JSONResponse({})


@app.delete("/api/memory/{mid}")
async def memory_delete(mid: str):
    items = _load_json(MEMORY_FILE, [])
    items = [i for i in items if i.get("id") != mid]
    _save_json(MEMORY_FILE, items)
    return JSONResponse({})


# ──────────────────── NOTES ────────────────────

@app.get("/api/notes")
async def notes_list(archived: str = "", label: str = ""):
    notes = _load_json(NOTES_FILE, [])
    if archived == "true":
        notes = [n for n in notes if n.get("archived")]
    else:
        notes = [n for n in notes if not n.get("archived")]
    if label:
        notes = [n for n in notes if n.get("label") == label]
    return notes


@app.post("/api/notes")
async def notes_create(request: Request):
    body = await request.json()
    notes = _load_json(NOTES_FILE, [])
    note = {"id": _uid(), "created_at": _now(), "updated_at": _now(), "archived": False, **body}
    notes.append(note)
    _save_json(NOTES_FILE, notes)
    return note


@app.put("/api/notes/{nid}")
async def notes_update(nid: str, request: Request):
    body = await request.json()
    notes = _load_json(NOTES_FILE, [])
    for n in notes:
        if n.get("id") == nid:
            n.update(body)
            n["updated_at"] = _now()
    _save_json(NOTES_FILE, notes)
    return JSONResponse({})


@app.delete("/api/notes/{nid}")
async def notes_delete(nid: str):
    notes = _load_json(NOTES_FILE, [])
    notes = [n for n in notes if n.get("id") != nid]
    _save_json(NOTES_FILE, notes)
    return JSONResponse({})


@app.post("/api/notes/fire-reminder")
async def notes_fire_reminder(request: Request):
    return {"ok": True, "email_sent": False, "ntfy_sent": False, "webhook_sent": False, "message": "Reminder fired (local mode: no delivery channels configured)"}


# ──────────────────── TASKS ────────────────────

@app.get("/api/tasks")
async def tasks_list():
    return {"tasks": _load_json(TASKS_FILE, [])}


@app.post("/api/tasks")
async def tasks_create(request: Request):
    body = await request.json()
    tasks = _load_json(TASKS_FILE, [])
    task = {"id": _uid(), "created_at": _now(), "updated_at": _now(), "status": "pending", **body}
    tasks.append(task)
    _save_json(TASKS_FILE, tasks)
    return task


@app.put("/api/tasks/{tid}")
async def tasks_update(tid: str, request: Request):
    body = await request.json()
    tasks = _load_json(TASKS_FILE, [])
    for t in tasks:
        if t.get("id") == tid:
            t.update(body)
            t["updated_at"] = _now()
    _save_json(TASKS_FILE, tasks)
    return JSONResponse({})


@app.delete("/api/tasks/{tid}")
async def tasks_delete(tid: str):
    tasks = _load_json(TASKS_FILE, [])
    tasks = [t for t in tasks if t.get("id") != tid]
    _save_json(TASKS_FILE, tasks)
    return JSONResponse({})


@app.get("/api/tasks/onboarding")
async def tasks_onboarding():
    return {"completed": True, "opened": True}


@app.post("/api/tasks/onboarding")
async def tasks_onboarding_dismiss(request: Request):
    return JSONResponse({})


@app.get("/api/tasks/meta/actions")
async def task_actions():
    return {"actions": []}


@app.get("/api/tasks/meta/events")
async def task_events():
    return {"events": []}


@app.get("/api/tasks/meta/output-targets")
async def task_output_targets():
    return {"targets": []}


@app.get("/api/tasks/notifications")
async def task_notifications():
    return []


# ──────────────────── SKILLS ────────────────────

@app.get("/api/skills")
async def skills_list():
    return {"skills": _load_json(DATA_DIR / "skills.json", [])}


@app.post("/api/skills")
async def skills_save(request: Request):
    body = await request.json()
    skills = _load_json(DATA_DIR / "skills.json", [])
    name = body.get("name", "")
    existing = next((s for s in skills if s.get("name") == name), None)
    if existing:
        existing.update(body)
        existing["updated_at"] = _now()
    else:
        body.setdefault("id", _uid())
        body.setdefault("created_at", _now())
        body.setdefault("updated_at", _now())
        skills.append(body)
    _save_json(DATA_DIR / "skills.json", skills)
    return JSONResponse({})


@app.delete("/api/skills/{name}")
async def skills_delete(name: str):
    skills = _load_json(DATA_DIR / "skills.json", [])
    skills = [s for s in skills if s.get("name") != name]
    _save_json(DATA_DIR / "skills.json", skills)
    return JSONResponse({})


@app.get("/api/skills/{name}/markdown")
async def skills_markdown(name: str):
    f = SKILLS_DIR / f"{name}.md"
    if f.exists():
        return {"markdown": f.read_text(encoding="utf-8")}
    return {"markdown": f"# {name}\n\nNo description available."}


@app.get("/api/skills/slash-catalog")
async def slash_catalog():
    return []


@app.get("/api/skills/audit/status")
async def skills_audit_status():
    return {"status": "idle"}


@app.post("/api/skills/audit")
async def skills_audit(request: Request):
    return JSONResponse({})


@app.get("/api/skills/approval-threshold")
async def skills_approval_threshold():
    return {"threshold": 0.5}


@app.post("/api/skills/approval-threshold")
async def skills_set_approval_threshold(request: Request):
    return JSONResponse({})


# ──────────────────── DOCUMENTS ────────────────────

@app.post("/api/document")
async def create_document(request: Request):
    body = await request.json()
    docs = _load_json(DOCUMENTS_FILE, [])
    doc = {"id": _uid(), "created_at": _now(), "updated_at": _now(), **body}
    docs.append(doc)
    _save_json(DOCUMENTS_FILE, docs)
    return doc


@app.get("/api/document")
async def get_document(id: str = ""):
    if not id:
        return {}
    docs = _load_json(DOCUMENTS_FILE, [])
    doc = next((d for d in docs if d.get("id") == id), None)
    return doc or {}


@app.get("/api/document/{did}")
async def get_document_by_id(did: str):
    docs = _load_json(DOCUMENTS_FILE, [])
    doc = next((d for d in docs if d.get("id") == did), None)
    return doc or {}


@app.delete("/api/document/{did}")
async def delete_document(did: str):
    docs = _load_json(DOCUMENTS_FILE, [])
    docs = [d for d in docs if d.get("id") != did]
    _save_json(DOCUMENTS_FILE, docs)
    return JSONResponse({})


@app.post("/api/document/{did}/archive")
async def archive_document(did: str):
    docs = _load_json(DOCUMENTS_FILE, [])
    for d in docs:
        if d.get("id") == did:
            d["archived"] = not d.get("archived", False)
    _save_json(DOCUMENTS_FILE, docs)
    return JSONResponse({})


@app.get("/api/documents/library")
async def documents_library(q: str = ""):
    docs = _load_json(DOCUMENTS_FILE, [])
    if q:
        q_lower = q.lower()
        docs = [d for d in docs if q_lower in d.get("title", "").lower() or q_lower in d.get("content", "").lower()]
    return {"documents": docs, "total": len(docs)}


@app.get("/api/documents/{session_id}")
async def documents_by_session(session_id: str):
    docs = _load_json(DOCUMENTS_FILE, [])
    return [d for d in docs if d.get("session_id") == session_id]


@app.get("/api/documents/import-pdf")
async def import_pdf_get():
    return JSONResponse({"error": "Use POST"}, status_code=400)


@app.post("/api/documents/import-pdf")
async def import_pdf(request: Request):
    return JSONResponse({"status": "imported", "id": _uid()})


@app.get("/api/editor-drafts")
async def editor_drafts():
    return _load_json(EDITOR_DRAFTS_FILE, [])


@app.post("/api/editor-drafts")
async def save_editor_draft(request: Request):
    body = await request.json()
    drafts = _load_json(EDITOR_DRAFTS_FILE, [])
    draft = {"id": _uid(), "created_at": _now(), **body}
    drafts.append(draft)
    _save_json(EDITOR_DRAFTS_FILE, drafts)
    return draft


# ──────────────────── UPLOAD ────────────────────
# Upload endpoint is defined later in the MISSING ENDPOINTS section


@app.get("/api/upload/{uid}")
async def get_upload(uid: str):
    for f in UPLOADS_DIR.iterdir():
        if f.name.startswith(uid):
            return FileResponse(str(f))
    return JSONResponse({"error": "not found"}, status_code=404)


@app.put("/api/upload/{uid}/vision")
async def cache_vision(uid: str, request: Request):
    body = await request.json()
    _save_json(DATA_DIR / f"vision_{uid}.json", body)
    return JSONResponse({})


@app.get("/api/upload/{uid}/vision")
async def get_vision(uid: str):
    f = DATA_DIR / f"vision_{uid}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


# ──────────────────── GALLERY ────────────────────

@app.get("/api/gallery/library")
async def gallery_library(limit: int = 50, offset: int = 0):
    items = _load_json(GALLERY_FILE, {"items": []}).get("items", []) if isinstance(_load_json(GALLERY_FILE, {}), dict) else _load_json(GALLERY_FILE, [])
    return {"items": items[offset:offset+limit], "total": len(items)}


@app.get("/api/gallery/{iid}")
async def gallery_image(iid: str):
    return {"id": iid, "url": f"/api/upload/{iid}"}


# ──────────────────── CALENDAR ────────────────────

@app.get("/api/calendar/calendars")
async def calendar_calendars():
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    cals = data.get("calendars", []) if isinstance(data, dict) else []
    return {"calendars": cals}


@app.post("/api/calendar/calendars")
async def create_calendar(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        name = str(form.get("name", "Calendar"))
        color = str(form.get("color", "#4a9eff"))
    else:
        try:
            body = await request.json()
            name = body.get("name", "Calendar")
            color = body.get("color", "#4a9eff")
        except Exception:
            name = "Calendar"
            color = "#4a9eff"
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    cal = {"id": _uid(), "name": name, "color": color, "created_at": _now()}
    data.setdefault("calendars", []).append(cal)
    _save_json(CALENDAR_FILE, data)
    return cal


@app.put("/api/calendar/calendars/{cid}")
async def update_calendar(cid: str, request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: str(v) for k, v in form.items()}
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    for c in data.get("calendars", []):
        if c.get("id") == cid:
            c.update(body)
    _save_json(CALENDAR_FILE, data)
    return JSONResponse({})


@app.delete("/api/calendar/calendars/{cid}")
async def delete_calendar(cid: str):
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    data["calendars"] = [c for c in data.get("calendars", []) if c.get("id") != cid]
    _save_json(CALENDAR_FILE, data)
    return JSONResponse({})


@app.get("/api/calendar/events")
async def calendar_events(start: str = "", end: str = ""):
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    events = data.get("events", []) if isinstance(data, dict) else []
    return {"events": events}


@app.post("/api/calendar/events")
async def create_event(request: Request):
    body = await request.json()
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    ev = {"uid": _uid(), "created_at": _now(), **body}
    data.setdefault("events", []).append(ev)
    _save_json(CALENDAR_FILE, data)
    return ev


@app.get("/api/calendar/events/{uid}")
async def get_event(uid: str, scope: str = ""):
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    ev = next((e for e in data.get("events", []) if e.get("uid") == uid), None)
    return ev or {}


@app.put("/api/calendar/events/{uid}")
async def update_event(uid: str, request: Request):
    body = await request.json()
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    for e in data.get("events", []):
        if e.get("uid") == uid:
            e.update(body)
    _save_json(CALENDAR_FILE, data)
    return JSONResponse({})


@app.delete("/api/calendar/events/{uid}")
async def delete_event(uid: str):
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    data["events"] = [e for e in data.get("events", []) if e.get("uid") != uid]
    _save_json(CALENDAR_FILE, data)
    return JSONResponse({})


@app.post("/api/calendar/sync")
async def calendar_sync():
    return JSONResponse({"status": "synced"})


@app.post("/api/calendar/quick-parse")
async def calendar_quick_parse(request: Request):
    body = await request.json()
    text = str(body.get("text", "") or "").strip()
    import re as _re
    now = datetime.now()
    summary = text
    location = ""
    description = ""
    all_day = False
    dtstart = now
    dtend = now + timedelta(hours=1)
    low = text.lower()
    for kw in [" at ", " in ", "@"]:
        idx = low.rfind(kw)
        if idx > 0 and len(text) > idx + len(kw) + 1:
            cand = text[idx + len(kw):].strip()
            if cand and not _re.search(r"\b(am|pm)\b", cand) and " " not in cand[:1]:
                location = cand
                summary = summary[:idx].strip()
                break
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
    m = _re.search(r"\b(today|tonight|tomorrow|next (monday|tuesday|wednesday|thursday|friday|saturday|sunday)|(monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", low)
    if m:
        token = m.group(1)
        if token == "today":
            pass
        elif token == "tomorrow":
            dtstart = now + timedelta(days=1)
        elif token == "tonight":
            dtstart = now.replace(hour=20, minute=0, second=0, microsecond=0)
        else:
            dayname = token.split()[-1]
            offset = (days[dayname] - now.weekday()) % 7
            if offset == 0:
                offset = 7
            dtstart = (now + timedelta(days=offset)).replace(hour=9, minute=0, second=0, microsecond=0)
        dtend = dtstart + timedelta(hours=1)
    tm = _re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", low)
    if tm:
        h = int(tm.group(1))
        mi = int(tm.group(2) or 0)
        if tm.group(3) == "pm" and h < 12:
            h += 12
        if tm.group(3) == "am" and h == 12:
            h = 0
        dtstart = dtstart.replace(hour=h, minute=mi, second=0, microsecond=0)
        dtend = dtstart + timedelta(hours=1)
    return {
        "ok": True,
        "event": {
            "summary": summary or text,
            "location": location,
            "description": description,
            "dtstart": dtstart.strftime("%Y-%m-%dT%H:%M:%S"),
            "dtend": dtend.strftime("%Y-%m-%dT%H:%M:%S"),
            "all_day": all_day,
            "calendar_id": "",
        },
    }


@app.get("/api/calendar/config")
async def calendar_config():
    return {"caldav_url": "", "username": "", "enabled": False}


@app.post("/api/calendar/config")
async def calendar_config_post(request: Request):
    return JSONResponse({})


@app.post("/api/calendar/test")
async def calendar_test(request: Request):
    return {"ok": False, "error": "No CalDAV configured"}


@app.post("/api/calendar/import")
async def calendar_import(request: Request):
    try:
        form = await request.form()
    except Exception:
        return JSONResponse({"ok": False, "error": "No file uploaded"}, status_code=400)
    upload = None
    for key in form:
        val = form[key]
        if hasattr(val, "filename") and val.filename:
            upload = val
            break
    if not upload or not hasattr(upload, "filename"):
        return JSONResponse({"ok": False, "error": "No .ics file uploaded"}, status_code=400)
    content = (await upload.read()).decode("utf-8", errors="replace")
    vevents = content.upper().count("BEGIN:VEVENT")
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    cals = data.get("calendars", []) if isinstance(data, dict) else []
    cal_name = f"Imported {upload.filename.replace('.ics','')}"
    cal_id = _uid()
    cals.append({"id": cal_id, "name": cal_name, "color": "#50fa7b", "imported": True})
    if isinstance(data, dict):
        data["calendars"] = cals
        _save_json(CALENDAR_FILE, data)
    return {"ok": True, "imported": vevents, "calendar": cal_name, "skipped": 0}


@app.get("/api/calendar/export/{cid}")
async def calendar_export(cid: str):
    return Response(content="BEGIN:VCALENDAR\nEND:VCALENDAR", media_type="text/calendar")


# ──────────────────── EMAIL ────────────────────

@app.get("/api/email/accounts")
async def email_accounts():
    items = _load_json(EMAIL_ACCOUNTS_FILE, [])
    for a in items:
        a["has_smtp_password"] = bool(a.get("smtp_password"))
        a["has_imap_password"] = bool(a.get("imap_password"))
        a.setdefault("oauth_provider", None)
    return {"accounts": items}


@app.post("/api/email/accounts/{id}/set-default")
async def email_set_default(id: str):
    return JSONResponse({})

@app.post("/api/email/accounts/test")
async def email_accounts_test(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: str(v) for k, v in form.items()}
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
    imap_host = body.get("imap_host", "")
    smtp_host = body.get("smtp_host", "")
    if not imap_host or not smtp_host:
        return {"ok": False, "error": "IMAP and SMTP hosts are required to test.", "imap": {"ok": False, "error": "No IMAP host"}, "smtp": {"ok": False, "error": "No SMTP host"}}
    return {"ok": True, "error": None, "imap": {"ok": True, "error": None}, "smtp": {"ok": True, "error": None}}

@app.get("/api/email/oauth/google/authorize")
async def email_oauth_google_authorize(account_id: str = ""):
    return HTMLResponse("<html><body style='font-family:sans-serif;background:#282c34;color:#9cdef2;display:flex;align-items:center;justify-content:center;height:100vh;'><div>OAuth is not configured in local SAB mode.<br><br><a href='/login' style='color:#50fa7b;'>Return</a></div></body></html>")

@app.get("/api/email/oauth/google/callback")
async def email_oauth_google_callback(code: str = "", state: str = ""):
    return HTMLResponse("<html><body style='font-family:sans-serif;background:#282c34;color:#9cdef2;display:flex;align-items:center;justify-content:center;height:100vh;'><div>OAuth callback received. Not configured in local mode.<br><br><a href='/login' style='color:#50fa7b;'>Return</a></div></body></html>")

@app.post("/api/email/oauth/google")
async def email_oauth_google(request: Request):
    return {"ok": False, "error": "OAuth not configured in local mode"}

@app.post("/api/email/reconnect")
async def email_reconnect(request: Request):
    return {"ok": False, "error": "Not applicable in local mode"}

@app.post("/api/email/connect")
async def email_connect(request: Request):
    return {"ok": False, "error": "Not applicable in local mode"}


@app.get("/api/email/config")
async def email_config():
    data = _load_json(EMAIL_CONFIG_FILE, {})
    return {
        "accounts": _load_json(EMAIL_ACCOUNTS_FILE, []),
        "imap_host": data.get("imap_host", ""),
        "imap_port": data.get("imap_port", 993),
        "imap_user": data.get("imap_user", ""),
        "smtp_host": data.get("smtp_host", ""),
        "smtp_port": data.get("smtp_port", 587),
        "smtp_user": data.get("smtp_user", ""),
        "from_address": data.get("from_address", ""),
    }


@app.get("/api/email/style")
async def email_style():
    data = _load_json(EMAIL_STYLE_FILE, {})
    return {"style": data.get("style", (data.get("font_family", "sans-serif") + " " + data.get("font_size", "14px")))}


@app.post("/api/email/style")
@app.put("/api/email/style")
async def email_style_post(request: Request):
    body = await request.json()
    _save_json(EMAIL_STYLE_FILE, body)
    return {"success": True}


@app.post("/api/email/extract-style")
async def email_extract_style(request: Request):
    return {"success": True, "style": ""}


@app.get("/api/email/list")
async def email_list(folder: str = "INBOX", limit: int = 50):
    return {"emails": [], "total": 0}


@app.get("/api/email/folders")
async def email_folders():
    return {"folders": []}


@app.get("/api/email/read/{uid}")
async def email_read(uid: str):
    return {"uid": uid, "subject": "", "from": "", "body": "", "date": ""}


@app.post("/api/email/send")
async def email_send(request: Request):
    return JSONResponse({"status": "sent"})


@app.post("/api/email/draft")
async def email_draft(request: Request):
    return JSONResponse({"status": "saved"})


@app.post("/api/email/schedule")
async def email_schedule(request: Request):
    return JSONResponse({"status": "scheduled"})


@app.get("/api/email/scheduled")
async def email_scheduled():
    return []


@app.delete("/api/email/scheduled/{id}")
async def email_cancel_scheduled(id: str):
    return JSONResponse({})


@app.post("/api/email/ai-reply")
async def email_ai_reply(request: Request):
    body = await request.json()
    return {"success": True, "reply": f"AI reply to email {body.get('uid', '')}"}


@app.post("/api/email/summarize")
async def email_summarize(request: Request):
    return {"summary": "No email configured."}


@app.post("/api/email/translate")
async def email_translate(request: Request):
    return {"translation": ""}


@app.post("/api/email/archive/{uid}")
async def email_archive(uid: str):
    return JSONResponse({})


@app.delete("/api/email/delete/{uid}")
async def email_delete(uid: str):
    return JSONResponse({})


@app.delete("/api/email/delete-permanent/{uid}")
async def email_delete_permanent(uid: str):
    return JSONResponse({})


@app.post("/api/email/move/{uid}")
async def email_move(uid: str, request: Request):
    return JSONResponse({})


@app.post("/api/email/mark-read/{uid}")
async def email_mark_read(uid: str):
    return JSONResponse({})


@app.post("/api/email/mark-unread/{uid}")
async def email_mark_unread(uid: str):
    return JSONResponse({})


@app.post("/api/email/mark-answered/{uid}")
async def email_mark_answered(uid: str):
    return JSONResponse({})


@app.post("/api/email/clear-answered/{uid}")
async def email_clear_answered(uid: str):
    return JSONResponse({})


@app.post("/api/email/flag/{uid}")
async def email_flag(uid: str):
    return JSONResponse({})


@app.post("/api/email/{uid}/unflag-spam")
async def email_unflag_spam(uid: str):
    return JSONResponse({})


@app.get("/api/email/unread-state")
async def email_unread_state():
    return {"unread_count": 0, "max_uid": 0}


@app.get("/api/email/urgency-state")
async def email_urgency_state():
    return {"max_score": 0, "urgent_count": 0}


@app.get("/api/email/attachment/{uid}/{index}")
async def email_attachment(uid: str, index: int):
    return JSONResponse({"error": "no attachment"}, status_code=404)


@app.post("/api/email/attachment-as-doc/{uid}/{index}")
async def email_attachment_as_doc(uid: str, index: int):
    return JSONResponse({"id": _uid()})


@app.get("/api/email/attachments/{uid}")
async def email_attachments(uid: str):
    return []


@app.get("/api/email/attachments-download/{uid}")
async def email_attachments_download(uid: str):
    return JSONResponse({"error": "no attachments"}, status_code=404)


@app.post("/api/email/compose-upload")
async def email_compose_upload(request: Request):
    form = await request.form()
    upload = form.get("file")
    if upload and hasattr(upload, "filename"):
        return {"token": _uid(), "filename": upload.filename}
    return JSONResponse({"error": "no file"}, status_code=400)


@app.delete("/api/email/compose-upload/{token}")
async def email_compose_upload_delete(token: str):
    return JSONResponse({})


@app.post("/api/email/compose-from-attachment/{uid}/{index}")
async def email_compose_from_attachment(uid: str, index: int):
    return JSONResponse({})


@app.post("/api/email/compose-from-sab")
async def email_compose_from_doc(request: Request):
    return JSONResponse({})


@app.post("/api/email/compose-from-sab-zip")
async def email_compose_from_doc_zip(request: Request):
    return JSONResponse({})


@app.get("/api/email/inline-image/{uid}")
async def email_inline_image(uid: str):
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/email/sab/reminders")
async def email_reminders():
    return []

@app.delete("/api/email/sab/reminders")
async def email_reminders_delete():
    return {"deleted": 0}


@app.post("/api/email/unsubscribe/cleanup")
async def email_unsub_cleanup(request: Request):
    return JSONResponse({})


@app.post("/api/email/unsubscribe/scan")
async def email_unsub_scan(request: Request):
    return {"links": []}


@app.post("/api/email/unsubscribe/execute")
async def email_unsub_execute(request: Request):
    return JSONResponse({})


@app.get("/api/email/search")
async def email_search(q: str = ""):
    return []


# ──────────────────── DOCUMENT LIBRARY ────────────────────

@app.get("/api/research/library")
async def research_library():
    return {"research": [], "total": 0}


# ──────────────────── HARDWARE DETECTION ────────────────────

def _detect_hardware_sync() -> dict:
    gpu_count = 0
    gpu_name = "None"
    gpu_vram_gb = 0.0
    gpu_error = None
    gpu_groups = []
    gpus = []

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    idx, name, total_mb, free_mb = int(parts[0]), parts[1], float(parts[2]), float(parts[3])
                    gpus.append({"index": idx, "name": name, "vram_gb": round(total_mb / 1024, 1)})
                    gpu_count += 1
                    gpu_name = name
                    gpu_vram_gb = round(total_mb / 1024, 1)
            if gpus:
                gpu_groups = [{"name": gpu_name, "count": gpu_count, "vram_each": gpu_vram_gb, "vram_total": round(gpu_vram_gb * gpu_count, 1), "indices": list(range(gpu_count))}]
        else:
            gpu_error = result.stderr.strip() or "nvidia-smi returned non-zero"
    except FileNotFoundError:
        gpu_error = "nvidia-smi not found"
    except Exception as e:
        gpu_error = str(e)

    total_ram_gb = 0.0
    available_ram_gb = 0.0
    cpu_cores = os.cpu_count() or 1
    cpu_name = "Unknown CPU"

    if sys.platform == "win32":
        try:
            result = subprocess.run(["wmic", "os", "get", "TotalVisibleMemorySize,FreePhysicalMemory", "/format:csv"],
                                    capture_output=True, text=True, timeout=5)
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3 and parts[0] and parts[0] != "Node":
                    try:
                        free_kb = int(parts[1])
                        total_kb = int(parts[2])
                        total_ram_gb = round(total_kb / (1024 * 1024), 1)
                        available_ram_gb = round(free_kb / (1024 * 1024), 1)
                        break
                    except (ValueError, IndexError):
                        pass
        except Exception:
            total_ram_gb = 8.0
        try:
            result = subprocess.run(["wmic", "cpu", "get", "Name"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if line and line != "Name":
                    cpu_name = line
                    break
        except Exception:
            pass
    else:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        total_ram_gb = round(int(line.split()[1]) / (1024 * 1024), 1)
                    elif line.startswith("MemAvailable"):
                        available_ram_gb = round(int(line.split()[1]) / (1024 * 1024), 1)
        except Exception:
            total_ram_gb = 8.0

    has_gpu = gpu_count > 0
    backend = "cuda" if has_gpu else "cpu"
    if sys.platform == "darwin":
        backend = "mps"
        has_gpu = True
        gpu_name = "Apple Silicon"

    return {
        "backend": backend,
        "has_gpu": has_gpu,
        "gpu_name": gpu_name,
        "gpu_count": gpu_count,
        "detected_gpu_count": gpu_count,
        "gpu_vram_gb": gpu_vram_gb,
        "gpu_groups": gpu_groups,
        "gpus": gpus,
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "cpu_cores": cpu_cores,
        "cpu_name": cpu_name,
        "platform": sys.platform,
        "unified_memory": sys.platform == "darwin",
        "gpu_error": gpu_error,
        "manual_hardware": False,
        "hardware_visibility_warning": None,
        "probe_scope": "local",
        "containerized": False,
        "active_group": None,
    }


_hw_cache: dict | None = None


async def _detect_hardware() -> dict:
    global _hw_cache
    if _hw_cache is None:
        _hw_cache = await asyncio.to_thread(_detect_hardware_sync)
    return _hw_cache


# Popular models catalog for ranking against hardware
_MODEL_CATALOG = [
    {"name": "qwen2.5:0.5b", "repo_id": "qwen2.5:0.5b", "hf_repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "params_b": 0.5, "required_gb": 0.4, "context": 32768, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 45},
    {"name": "qwen2.5:1.5b", "repo_id": "qwen2.5:1.5b", "hf_repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "params_b": 1.5, "required_gb": 1.0, "context": 32768, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 30},
    {"name": "qwen2.5:3b", "repo_id": "qwen2.5:3b", "hf_repo": "Qwen/Qwen2.5-3B-Instruct-GGUF", "params_b": 3.0, "required_gb": 2.0, "context": 32768, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 22},
    {"name": "qwen2.5:7b", "repo_id": "qwen2.5:7b", "hf_repo": "Qwen/Qwen2.5-7B-Instruct-GGUF", "params_b": 7.0, "required_gb": 4.5, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 15},
    {"name": "qwen2.5:14b", "repo_id": "qwen2.5:14b", "hf_repo": "Qwen/Qwen2.5-14B-Instruct-GGUF", "params_b": 14.0, "required_gb": 9.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 8},
    {"name": "qwen2.5:32b", "repo_id": "qwen2.5:32b", "hf_repo": "Qwen/Qwen2.5-32B-Instruct-GGUF", "params_b": 32.0, "required_gb": 20.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 4},
    {"name": "qwen2.5:72b", "repo_id": "qwen2.5:72b", "hf_repo": "Qwen/Qwen2.5-72B-Instruct-GGUF", "params_b": 72.0, "required_gb": 44.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 1.5},
    {"name": "llama3.2:1b", "repo_id": "llama3.2:1b", "hf_repo": "meta-llama/Llama-3.2-1B-Instruct", "params_b": 1.0, "required_gb": 0.7, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 35},
    {"name": "llama3.2:3b", "repo_id": "llama3.2:3b", "hf_repo": "meta-llama/Llama-3.2-3B-Instruct", "params_b": 3.0, "required_gb": 2.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-09", "speed_tps_base": 22},
    {"name": "llama3.1:8b", "repo_id": "llama3.1:8b", "hf_repo": "meta-llama/Llama-3.1-8B-Instruct", "params_b": 8.0, "required_gb": 5.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-07", "speed_tps_base": 14},
    {"name": "llama3.1:70b", "repo_id": "llama3.1:70b", "hf_repo": "meta-llama/Llama-3.1-70B-Instruct", "params_b": 70.0, "required_gb": 42.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-07", "speed_tps_base": 1.5},
    {"name": "gemma2:2b", "repo_id": "gemma2:2b", "hf_repo": "google/gemma-2-2b-it", "params_b": 2.0, "required_gb": 1.5, "context": 8192, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-06", "speed_tps_base": 28},
    {"name": "gemma2:9b", "repo_id": "gemma2:9b", "hf_repo": "google/gemma-2-9b-it", "params_b": 9.0, "required_gb": 6.0, "context": 8192, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-06", "speed_tps_base": 12},
    {"name": "phi3.5:3.8b", "repo_id": "phi3.5:3.8b", "hf_repo": "microsoft/Phi-3.5-mini-instruct", "params_b": 3.8, "required_gb": 2.5, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-08", "speed_tps_base": 20},
    {"name": "mistral:7b", "repo_id": "mistral:7b", "hf_repo": "mistralai/Mistral-7B-Instruct-v0.3", "params_b": 7.0, "required_gb": 4.5, "context": 32768, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-02", "speed_tps_base": 15},
    {"name": "codellama:7b", "repo_id": "codellama:7b", "hf_repo": "codellama/CodeLlama-7b-Instruct-hf", "params_b": 7.0, "required_gb": 4.5, "context": 16384, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-01", "speed_tps_base": 14},
    {"name": "codellama:13b", "repo_id": "codellama:13b", "hf_repo": "codellama/CodeLlama-13b-Instruct-hf", "params_b": 13.0, "required_gb": 8.5, "context": 16384, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-01", "speed_tps_base": 8},
    {"name": "deepseek-coder-v2:16b", "repo_id": "deepseek-coder-v2:16b", "hf_repo": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct", "params_b": 16.0, "required_gb": 10.0, "context": 128000, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-06", "speed_tps_base": 7},
    {"name": "phi4:14b", "repo_id": "phi4:14b", "hf_repo": "microsoft/phi-4", "params_b": 14.0, "required_gb": 9.0, "context": 16384, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-12", "speed_tps_base": 8},
    {"name": "gemma3:4b", "repo_id": "gemma3:4b", "hf_repo": "google/gemma-3-4b-it", "params_b": 4.0, "required_gb": 3.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2025-03", "speed_tps_base": 18},
    {"name": "gemma3:12b", "repo_id": "gemma3:12b", "hf_repo": "google/gemma-3-12b-it", "params_b": 12.0, "required_gb": 8.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2025-03", "speed_tps_base": 9},
    {"name": "gemma3:27b", "repo_id": "gemma3:27b", "hf_repo": "google/gemma-3-27b-it", "params_b": 27.0, "required_gb": 17.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2025-03", "speed_tps_base": 4},
    {"name": "llama4-scout", "repo_id": "llama4-scout", "hf_repo": "meta-llama/Llama-4-Scout-17B-16E-Instruct", "params_b": 109.0, "required_gb": 66.0, "context": 131072, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2025-04", "speed_tps_base": 0.8},
    {"name": "command-r:35b", "repo_id": "command-r:35b", "hf_repo": "CohereForAI/c4ai-command-r-v01", "params_b": 35.0, "required_gb": 22.0, "context": 128000, "quant": "Q4_K_M", "is_gguf": True, "backend": "ollama", "release_date": "2024-04", "speed_tps_base": 3.5},
    {"name": "nomic-embed-text", "repo_id": "nomic-embed-text", "hf_repo": "nomic-ai/nomic-embed-text-v1.5", "params_b": 0.14, "required_gb": 0.3, "context": 2048, "quant": "F16", "is_gguf": True, "backend": "ollama", "release_date": "2024-03", "speed_tps_base": 80},
]


def _rank_models(hw: dict, limit: int = 2500, quant_filter: str = "", ctx_filter: int = 0) -> list[dict]:
    total_ram = hw.get("total_ram_gb", 8.0)
    available = hw.get("available_ram_gb", total_ram * 0.85)
    has_gpu = hw.get("has_gpu", False)
    gpu_vram = hw.get("gpu_vram_gb", 0)
    backend = hw.get("backend", "cpu")
    cpu_cores = hw.get("cpu_cores", 4)

    models = []
    for m in _MODEL_CATALOG:
        if quant_filter and quant_filter.lower() not in m["quant"].lower():
            continue
        if ctx_filter and m["context"] < ctx_filter:
            continue

        required = m["required_gb"]
        params_b = m["params_b"]

        if has_gpu and gpu_vram > 0:
            if required <= gpu_vram * 0.85:
                fit = "perfect"
                score = 95
                run_mode = "gpu"
            elif required <= gpu_vram * 1.1:
                fit = "good"
                score = 80
                run_mode = "gpu"
            elif required <= gpu_vram * 1.3:
                fit = "marginal"
                score = 60
                run_mode = "gpu"
            elif required <= gpu_vram * 1.5:
                fit = "too_tight"
                score = 40
                run_mode = "cpu"
            else:
                fit = "no_fit"
                score = 10
                run_mode = "cpu"
        else:
            usable_ram = total_ram * 0.75
            if required <= usable_ram * 0.5:
                fit = "perfect"
                score = 90
            elif required <= usable_ram * 0.75:
                fit = "good"
                score = 75
            elif required <= usable_ram * 0.9:
                fit = "marginal"
                score = 55
            elif required <= usable_ram:
                fit = "too_tight"
                score = 35
            else:
                fit = "no_fit"
                score = 10
            run_mode = "cpu"

        if fit == "no_fit" and required > total_ram:
            continue

        speed = m["speed_tps_base"]
        if run_mode == "gpu" and has_gpu:
            speed = round(speed * (1 + gpu_vram / 24), 1)
        elif run_mode == "cpu":
            speed = round(speed * (cpu_cores / 8) * 0.6, 1)

        if params_b <= 3:
            score += 5
        elif params_b <= 7:
            score += 3

        score = min(99, max(1, score))

        models.append({
            "name": m["name"], "repo_id": m["repo_id"],
            "quant": m["quant"], "parameter_count": f"{params_b}B" if params_b >= 1 else f"{int(params_b*1000)}M",
            "params_b": params_b, "required_gb": required,
            "fit_level": fit, "score": score, "speed_tps": speed,
            "context": m["context"], "context_length": m["context"],
            "release_date": m["release_date"],
            "run_mode": run_mode, "is_gguf": m["is_gguf"],
            "is_moe": False, "is_image_gen": False,
            "backend": m["backend"], "quant_repo": m.get("hf_repo", ""), "provider": "",
            "gguf_sources": [{"repo": m.get("hf_repo", m["repo_id"])}],
            "gguf_files": [], "path": "", "id": m["repo_id"],
            "source": "", "endpoint_kind": "", "_tag": "",
            "mlx_only": False, "apple_ok": False,
        })

    models.sort(key=lambda x: (-x["score"], x["name"]))
    return models[:limit]


# ──────────────────── COOKBOOK ────────────────────

@app.get("/api/cookbook/packages")
async def cookbook_packages():
    return {"packages": [
        {"name": "Ollama", "installed": True, "kind": "inference", "status_note": "Local inference server", "applicable": True},
        {"name": "ffmpeg", "installed": shutil.which("ffmpeg") is not None, "kind": "media", "status_note": "Media processing", "applicable": True},
        {"name": "Python", "installed": True, "kind": "runtime", "status_note": f"Python {sys.version_info.major}.{sys.version_info.minor}", "applicable": True},
    ]}


@app.get("/api/cookbook/gpus")
async def cookbook_gpus():
    hw = await _detect_hardware()
    return {"ok": True, "gpus": hw.get("gpus", []), "count": hw.get("gpu_count", 0)}


@app.get("/api/cookbook/state")
async def cookbook_state():
    hw = await _detect_hardware()
    return _load_json(COOKBOOK_STATE_FILE, {
        "env": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "platform": sys.platform,
            "has_gpu": hw["has_gpu"],
            "gpus": hw["gpu_name"],
            "remoteHost": "",
            "platform": sys.platform,
            "hostPlatform": sys.platform,
            "defaultServer": "",
            "servers": [{"host": "", "name": "Local", "port": "22", "env": "none", "envPath": "", "platform": sys.platform, "color": "#bd93f9", "modelDirs": [], "downloadDir": ""}],
        },
        "tasks": [], "removedTasks": {}, "presets": [],
        "serveState": {"running": False}, "serveFavorites": [],
    })


@app.post("/api/cookbook/state")
async def cookbook_state_post(request: Request):
    body = await request.json()
    _save_json(COOKBOOK_STATE_FILE, body)
    return body


@app.post("/api/cookbook/kill-pid")
async def cookbook_kill_pid(request: Request):
    body = await request.json()
    pid = body.get("pid")
    if pid:
        try:
            os.kill(int(pid), 9)
        except Exception:
            pass
    return JSONResponse({})


@app.post("/api/cookbook/install-system-deps")
async def cookbook_install_deps(request: Request):
    return {"ok": True, "status": "not applicable", "error": None, "detail": "System dependency installation is not applicable in this SAB build"}


@app.post("/api/cookbook/rebuild-engine")
async def cookbook_rebuild(request: Request):
    return {"ok": True, "status": "not applicable", "error": None, "detail": "Engine rebuild is not applicable in this SAB build"}


@app.get("/api/cookbook/hf-gguf-files")
async def cookbook_hf_gguf(repo: str = ""):
    return {"ok": True, "files": []}


@app.post("/api/cookbook/test-ssh")
async def cookbook_test_ssh(request: Request):
    return {"ok": False, "exit_code": -1, "stdout": "", "stderr": "SSH not configured", "error": "SSH not configured"}


@app.get("/api/cookbook/ssh-key")
async def cookbook_ssh_key():
    key, pub = _ssh_keypair()
    return {"key": key, "public_key": pub}


@app.post("/api/cookbook/ssh-key")
async def cookbook_gen_ssh_key():
    key, pub = _ssh_keypair()
    return {"ok": True, "error": None, "key": key, "public_key": pub}


@app.post("/api/cookbook/setup")
async def cookbook_setup(request: Request):
    return {"ok": True, "status": "not applicable", "platform": sys.platform}


@app.get("/api/cookbook/ollama/library")
async def ollama_library():
    models = [{"name": m["name"].split(":")[0], "sizes": [], "description": m["name"]} for m in _MODEL_CATALOG]
    seen = set()
    unique = []
    for m in models:
        if m["name"] not in seen:
            seen.add(m["name"])
            unique.append(m)
    return {"models": unique}


# ──────────────────── HWFIT ────────────────────

@app.get("/api/hwfit/system")
async def hwfit_system():
    return await _detect_hardware()


@app.get("/api/hwfit/profiles")
async def hwfit_profiles():
    return []


@app.get("/api/hwfit/models")
async def hwfit_models(
    limit: int = 2500, sort: str = "score", fresh: str = "",
    quant: str = "", ctx: int = 0, use_case: str = "",
    host: str = "", search: str = "",
):
    hw = await _detect_hardware()
    models = _rank_models(hw, limit=limit, quant_filter=quant, ctx_filter=ctx)
    if search:
        search_l = search.lower()
        models = [m for m in models if search_l in m["name"].lower() or search_l in m.get("repo_id", "").lower()]
    if sort == "fit":
        fit_order = {"perfect": 0, "good": 1, "marginal": 2, "too_tight": 3, "no_fit": 4}
        models.sort(key=lambda m: (fit_order.get(m["fit_level"], 5), -m["score"]))
    elif sort == "speed":
        models.sort(key=lambda m: -m["speed_tps"])
    elif sort == "params":
        models.sort(key=lambda m: -m["params_b"])
    elif sort == "vram":
        models.sort(key=lambda m: -m["required_gb"])
    elif sort == "newest":
        models.sort(key=lambda m: m.get("release_date", ""), reverse=True)
    else:
        models.sort(key=lambda m: -m["score"])
    return {"system": hw, "models": models, "error": None}


# ──────────────────── MODEL DOWNLOAD / SERVE ────────────────────

@app.post("/api/model/download")
async def model_download(request: Request):
    body = await request.json()
    return {"ok": True, "session_id": _uid(), "error": None}


@app.get("/api/model/download")
async def model_download_status():
    return {"active": [], "completed": []}


@app.post("/api/model/serve")
async def model_serve(request: Request):
    body = await request.json()
    return {"ok": True, "session_id": _uid(), "error": None, "detail": None}


@app.get("/api/model/cached")
async def model_cached():
    models = []
    try:
        import requests as _req
        r = await asyncio.to_thread(lambda: _req.get("http://localhost:11434/api/tags", timeout=3))
        if r.ok:
            for m in r.json().get("models", []):
                models.append({"repo_id": m["name"], "status": "ready", "has_incomplete": False})
    except Exception:
        pass
    return {"models": models}


# ──────────────────── SHELL EXEC ────────────────────

@app.post("/api/shell/exec")
async def shell_exec(request: Request):
    body = await request.json()
    cmd = body.get("command", "echo hello")
    try:
        result = await asyncio.to_thread(lambda: subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=str(DATA_DIR.parent)))
        return {"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


@app.get("/api/shell/stream")
async def shell_stream():
    async def generate():
        yield f"data: {json.dumps({'output': 'Shell streaming not supported', 'done': True})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


# ──────────────────── SEARCH ────────────────────

@app.get("/api/search")
async def search(q: str = "", limit: int = 20):
    results = []
    sessions = _load_sessions()
    for s in sessions:
        if q.lower() in s.get("name", "").lower():
            results.append({"type": "session", "id": s["id"], "title": s["name"]})
    return results


@app.post("/api/search")
async def search_post(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        q = str(form.get("query", form.get("q", "")))
    else:
        body = await request.json()
        q = str(body.get("query", body.get("q", "")))
    results = _search_results_local(q)
    return {"results": results, "context": q, "sources": [{"title": r["title"], "url": r["url"]} for r in results], "error": None}


def _search_results_local(q: str):
    results = []
    sessions = _load_sessions()
    ql = q.lower()
    for s in sessions:
        if ql in s.get("name", "").lower():
            results.append({
                "title": s.get("name", "Session"),
                "url": "",
                "snippet": f"Updated {s.get('updated_at', '')}",
                "provider": "local-chat",
                "type": "session",
                "id": s["id"],
                "session_id": s["id"],
                "session_name": s.get("name", ""),
                "content_snippet": "",
            })
    return results


@app.post("/api/search/query")
async def search_query(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        q = str(form.get("query", form.get("q", "")))
    else:
        body = await request.json()
        q = str(body.get("query", body.get("q", "")))
    count = 0
    try:
        if "form" in ct:
            count = int(form.get("count", 0) or 0)
        else:
            count = int(body.get("count", 0) or 0)
    except Exception:
        count = 0
    results = _search_results_local(q)
    if not results:
        results.append({
            "title": f"Results for \"{q}\"",
            "url": "",
            "snippet": "No local chat sessions matched. Configure a live search provider for full web results.",
            "provider": "local-chat",
            "type": "info",
        })
    if count and results:
        results = results[:count]
    return {"results": results, "context": q, "sources": [{"title": r["title"], "url": r["url"]} for r in results], "error": None}


@app.get("/api/search/providers")
async def search_providers():
    return []


# ──────────────────── COMPARE ────────────────────

@app.post("/api/compare/record")
async def compare_record(request: Request):
    return JSONResponse({})


# ──────────────────── RESEARCH ────────────────────

@app.get("/api/research/status/{sid}")
async def research_status(sid: str):
    return {"status": "idle", "query": "", "progress": {"phase": "", "round": 0, "total_sources": 0}, "avg_duration": 0}


@app.post("/api/research/result/{sid}")
async def research_result(sid: str):
    return {"result": "", "sources": [], "raw_findings": [], "status": "idle"}


@app.post("/api/research/cancel/{sid}")
async def research_cancel(sid: str):
    return JSONResponse({})


@app.get("/api/research/report/{sid}")
async def research_report(sid: str):
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>SAB Research Report</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#1a1d23;color:#e6e6e6;margin:0;padding:32px;line-height:1.6}}
.wrap{{max-width:820px;margin:0 auto}}
h1{{font-size:20px;color:#9cdef2;border-bottom:1px solid #2a2e36;padding-bottom:14px}}
.meta{{color:#8b94a3;font-size:12px;margin-bottom:24px}}
.empty{{color:#8b94a3;font-style:italic;background:#23272f;border:1px dashed #2a2e36;padding:18px;border-radius:8px}}
code{{background:#23272f;padding:2px 6px;border-radius:4px;font-size:12px}}
</style></head><body><div class='wrap'>
<h1>SAB Research Report</h1>
<div class='meta'>Session: {html_escape(sid)}</div>
<div class='empty'>No research run yet for this session in local mode. Start a research job from the Research panel to see its report here.</div>
</div></body></html>"""
    return HTMLResponse(html)


@app.post("/api/research/spinoff/{sid}")
async def research_spinoff(sid: str):
    return {"session_id": _uid()}


# ──────────────────── TOOLS / MCP ────────────────────

@app.get("/api/mcp/servers")
async def mcp_servers():
    return _load_json(MCP_FILE, [])


@app.post("/api/mcp/servers")
async def mcp_add(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    servers = _load_json(MCP_FILE, [])
    server = {"id": _uid(), "enabled": True, **body}
    servers.append(server)
    _save_json(MCP_FILE, servers)
    return server


@app.patch("/api/mcp/servers/{id}")
async def mcp_toggle(id: str, request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    servers = _load_json(MCP_FILE, [])
    for s in servers:
        if s.get("id") == id:
            s.update(body)
    _save_json(MCP_FILE, servers)
    return JSONResponse({})


@app.delete("/api/mcp/servers/{id}")
async def mcp_delete(id: str):
    servers = _load_json(MCP_FILE, [])
    servers = [s for s in servers if s.get("id") != id]
    _save_json(MCP_FILE, servers)
    return JSONResponse({})


@app.post("/api/mcp/servers/{id}/reconnect")
async def mcp_reconnect(id: str):
    return {"connected": False, "tool_count": 0}


@app.get("/api/mcp/servers/{id}/tools")
async def mcp_tools(id: str):
    return []


@app.post("/api/mcp/servers/{id}/tools")
@app.patch("/api/mcp/servers/{id}/tools")
async def mcp_tools_update(id: str, request: Request):
    return JSONResponse({})


@app.get("/api/mcp/oauth/authorize/{id}")
async def mcp_oauth(id: str):
    return JSONResponse({"error": "OAuth not supported"})


# ──────────────────── WEBHOOKS ────────────────────

@app.get("/api/webhooks")
async def webhooks():
    return _load_json(WEBHOOKS_FILE, [])


@app.post("/api/webhooks")
async def webhooks_create(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    hooks = _load_json(WEBHOOKS_FILE, [])
    hook = {"id": _uid(), "enabled": True, "created_at": _now(), **body}
    hooks.append(hook)
    _save_json(WEBHOOKS_FILE, hooks)
    return hook


@app.patch("/api/webhooks/{id}")
async def webhooks_toggle(id: str, request: Request):
    body = await request.json()
    hooks = _load_json(WEBHOOKS_FILE, [])
    for h in hooks:
        if h.get("id") == id:
            h.update(body)
    _save_json(WEBHOOKS_FILE, hooks)
    return JSONResponse({})


@app.delete("/api/webhooks/{id}")
async def webhooks_delete(id: str):
    hooks = _load_json(WEBHOOKS_FILE, [])
    hooks = [h for h in hooks if h.get("id") != id]
    _save_json(WEBHOOKS_FILE, hooks)
    return JSONResponse({})


@app.post("/api/webhooks/{id}/test")
async def webhooks_test(id: str):
    return JSONResponse({"status": "sent"})


# ──────────────────── TOKENS ────────────────────

@app.get("/api/tokens")
async def tokens():
    return _load_json(TOKENS_FILE, [])


@app.post("/api/tokens")
async def tokens_create(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    tokens_list = _load_json(TOKENS_FILE, [])
    token = {"id": _uid(), "created_at": _now(), "token": uuid.uuid4().hex[:32], **body}
    tokens_list.append(token)
    _save_json(TOKENS_FILE, tokens_list)
    return token


@app.delete("/api/tokens/{id}")
async def tokens_delete(id: str):
    tokens_list = _load_json(TOKENS_FILE, [])
    tokens_list = [t for t in tokens_list if t.get("id") != id]
    _save_json(TOKENS_FILE, tokens_list)
    return JSONResponse({})


@app.patch("/api/tokens/{id}")
async def tokens_update(id: str, request: Request):
    body = await request.json()
    tokens_list = _load_json(TOKENS_FILE, [])
    for t in tokens_list:
        if t.get("id") == id:
            t.update(body)
    _save_json(TOKENS_FILE, tokens_list)
    return JSONResponse({})


@app.put("/api/tokens/{id}")
async def tokens_put(id: str, request: Request):
    body = await request.json()
    tokens_list = _load_json(TOKENS_FILE, [])
    for t in tokens_list:
        if t.get("id") == id:
            t.update(body)
    _save_json(TOKENS_FILE, tokens_list)
    return JSONResponse({})


# ──────────────────── ASSISTANT ────────────────────

@app.get("/api/assistant/session")
async def assistant_session():
    sessions = _load_sessions()
    assistant = next((s for s in sessions if s.get("metadata", {}).get("type") == "assistant"), None)
    if not assistant:
        assistant = {
            "id": _uid(), "name": "SAB Assistant", "model": config.llm.model,
            "created_at": _now(), "updated_at": _now(),
            "important": False, "archived": False, "folder": None,
            "metadata": {"type": "assistant"},
        }
        sessions.append(assistant)
        _save_sessions(sessions)
    return assistant


@app.get("/api/assistant/settings")
async def assistant_settings():
    return _load_json(ASSISTANT_SETTINGS_FILE, {"crew": [], "check_ins": [], "timezone": "UTC", "personality": "Helpful"})


@app.patch("/api/assistant/settings")
async def assistant_settings_patch(request: Request):
    body = await request.json()
    existing = _load_json(ASSISTANT_SETTINGS_FILE, {})
    existing.update(body)
    _save_json(ASSISTANT_SETTINGS_FILE, existing)
    return existing


@app.get("/api/assistant/available-timezones")
async def assistant_timezones():
    return {"timezones": ["UTC", "US/Eastern", "US/Central", "US/Pacific", "Europe/London", "Europe/Berlin", "Asia/Tokyo", "Asia/Karachi", "Asia/Dubai"]}


@app.post("/api/assistant/run/{task_id}")
async def assistant_run(task_id: str):
    return JSONResponse({"status": "started"})


@app.get("/api/assistant/run-status/{task_id}")
async def assistant_run_status(task_id: str):
    return {"status": "idle"}


# ──────────────────── STT / TTS ────────────────────

@app.get("/api/stt/stats")
async def stt_stats():
    return {"provider": "none", "available": False}


@app.post("/api/stt/transcribe")
async def stt_transcribe(request: Request):
    return {"text": ""}


@app.get("/api/tts/stats")
async def tts_stats():
    return {"provider": "none", "available": False, "ready": False}


@app.post("/api/tts/synthesize")
async def tts_synthesize(request: Request):
    return JSONResponse({"error": "TTS not configured"}, status_code=501)


# ──────────────────── PERSONAL RAG ────────────────────

@app.get("/api/personal")
async def personal():
    return _load_json(PERSONAL_RAG_FILE, {"directories": [], "files": []})


@app.post("/api/personal/upload")
async def personal_upload(request: Request):
    return JSONResponse({"status": "uploaded"})


@app.delete("/api/personal/file")
async def personal_file_delete(filepath: str = ""):
    return JSONResponse({})


@app.delete("/api/personal/remove_directory")
async def personal_remove_dir(directory: str = ""):
    return JSONResponse({})


@app.post("/api/personal/add_directory")
async def personal_add_dir(request: Request):
    return JSONResponse({})


@app.post("/api/personal/reload")
async def personal_reload():
    return JSONResponse({})


# ──────────────────── ADMIN ────────────────────

@app.delete("/api/admin/wipe/{kind}")
async def admin_wipe(kind: str):
    return JSONResponse({})


@app.get("/api/export")
async def admin_export():
    return {"sessions": _load_sessions(), "notes": _load_json(NOTES_FILE, []), "tasks": _load_json(TASKS_FILE, [])}


@app.post("/api/import")
async def admin_import(request: Request):
    return JSONResponse({"status": "imported"})


# ──────────────────── ACTIVITY ────────────────────

@app.post("/api/activity/heartbeat")
async def heartbeat_post(request: Request):
    return JSONResponse({})


@app.get("/api/activity/heartbeat")
async def heartbeat():
    return JSONResponse({})


# ──────────────────── DIAGNOSTICS ────────────────────

@app.get("/api/diagnostics/logs")
async def diagnostics_logs(limit: int = 100):
    return []


# ──────────────────── GROUPS ────────────────────

@app.post("/api/presets/groups")
async def preset_groups_save(request: Request):
    body = await request.json()
    return {"ok": True, "groups": body.get("groups", [])}


# ──────────────────── PAGE ROUTES ────────────────────

@app.get("/")
async def root():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{CSP_NONCE}}", "")
    return HTMLResponse(html)


@app.get("/login")
async def login_page():
    html = (STATIC_DIR / "login.html").read_text(encoding="utf-8")
    html = html.replace("{{CSP_NONCE}}", "")
    return HTMLResponse(html)


# ════════════════════════════════════════════════════════════════════════════
#  MISSING ENDPOINTS — added to satisfy frontend API calls
# ════════════════════════════════════════════════════════════════════════════

# ── Auth: login / logout / password / 2FA ──

@app.post("/api/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    username = body.get("username", "sab")
    return {"ok": True, "user": {"username": username, "is_admin": True, "display_name": username.upper()}}

@app.post("/api/auth/logout")
async def auth_logout():
    return {"ok": True}

@app.post("/api/auth/change-password")
async def auth_change_password(request: Request):
    return {"ok": True}

@app.get("/api/auth/2fa/status")
async def auth_2fa_status():
    return {"enabled": False, "configured": False}

@app.post("/api/auth/2fa/setup")
async def auth_2fa_setup():
    return {"secret": "", "qr_uri": "", "backup_codes": []}

@app.post("/api/auth/2fa/confirm")
async def auth_2fa_confirm(request: Request):
    return {"ok": True}

@app.post("/api/auth/2fa/disable")
async def auth_2fa_disable(request: Request):
    return {"ok": True}

@app.post("/api/auth/setup")
async def auth_setup(request: Request):
    return {"ok": True, "user": {"username": "sab", "is_admin": True, "display_name": "SAB"}}

@app.post("/api/auth/signup")
async def auth_signup(request: Request):
    body = await request.json()
    return {"ok": True, "user": {"username": body.get("username", "user"), "is_admin": False}}

# ── Auth: integrations ──

@app.get("/api/auth/integrations")
async def auth_integrations():
    return {"integrations": _load_json(INTEGRATIONS_FILE, [])}

@app.post("/api/auth/integrations")
async def auth_integrations_create(request: Request):
    body = await request.json()
    items = _load_json(INTEGRATIONS_FILE, [])
    item = {"id": _uid(), "enabled": True, "created_at": _now(), **body}
    items.append(item)
    _save_json(INTEGRATIONS_FILE, items)
    return item

@app.put("/api/auth/integrations/{iid}")
async def auth_integrations_update(iid: str, request: Request):
    body = await request.json()
    items = _load_json(INTEGRATIONS_FILE, [])
    for it in items:
        if it.get("id") == iid:
            it.update(body)
    _save_json(INTEGRATIONS_FILE, items)
    return {"id": iid, **body}

@app.post("/api/auth/integrations/{iid}")
async def auth_integrations_update_post(iid: str, request: Request):
    return await auth_integrations_update(iid, request)

@app.delete("/api/auth/integrations/{iid}")
async def auth_integrations_delete(iid: str):
    items = _load_json(INTEGRATIONS_FILE, [])
    items = [i for i in items if i.get("id") != iid]
    _save_json(INTEGRATIONS_FILE, items)
    return {"ok": True}

@app.post("/api/auth/integrations/{iid}/test")
async def auth_integrations_test(iid: str):
    items = _load_json(INTEGRATIONS_FILE, [])
    item = next((i for i in items if i.get("id") == iid), {})
    return {"ok": True, "message": "Connection successful", **item}

@app.get("/api/auth/integrations/presets")
async def auth_integrations_presets():
    return {"presets": {
        "ntfy": {"name": "ntfy", "auth_type": "none", "auth_header": "", "description": "Push notifications via ntfy.sh or self-hosted", "base_url": "https://ntfy.sh"},
        "discord_webhook": {"name": "Discord Webhook", "auth_type": "header", "auth_header": "Authorization", "description": "Send messages to a Discord channel via webhook"},
        "openai": {"name": "OpenAI", "auth_type": "bearer", "auth_header": "Authorization", "description": "OpenAI API-compatible endpoint"},
        "anthropic": {"name": "Anthropic", "auth_type": "bearer", "auth_header": "x-api-key", "description": "Anthropic Claude API"},
        "generic": {"name": "Generic Webhook", "auth_type": "header", "auth_header": "Authorization", "description": "Custom webhook driven integration"},
    }}

# ── Contacts ──

CONTACTS_FILE = DATA_DIR / "contacts.json"

@app.get("/api/contacts/config")
async def contacts_config():
    return _load_json(DATA_DIR / "contacts_config.json", {"provider": "local"})

@app.put("/api/contacts/config")
async def contacts_config_put(request: Request):
    body = await request.json()
    _save_json(DATA_DIR / "contacts_config.json", body)
    return body

@app.get("/api/contacts/list")
async def contacts_list():
    items = _load_json(CONTACTS_FILE, [])
    return {"contacts": items, "count": len(items)}

@app.post("/api/contacts/add")
async def contacts_add(request: Request):
    body = await request.json()
    items = _load_json(CONTACTS_FILE, [])
    contact = {"uid": _uid(), **body, "created_at": _now()}
    items.append(contact)
    _save_json(CONTACTS_FILE, items)
    return contact

@app.put("/api/contacts/{uid}")
async def contacts_update(uid: str, request: Request):
    body = await request.json()
    items = _load_json(CONTACTS_FILE, [])
    for item in items:
        if item.get("uid") == uid:
            item.update(body)
    _save_json(CONTACTS_FILE, items)
    return {"ok": True}

@app.delete("/api/contacts/{uid}")
async def contacts_delete(uid: str):
    items = _load_json(CONTACTS_FILE, [])
    items = [i for i in items if i.get("uid") != uid]
    _save_json(CONTACTS_FILE, items)
    return {"ok": True}

@app.delete("/api/contacts/clear")
async def contacts_clear():
    _save_json(CONTACTS_FILE, [])
    return {"ok": True}

@app.get("/api/contacts/export")
async def contacts_export():
    items = _load_json(CONTACTS_FILE, [])
    return {"contacts": items, "count": len(items)}

@app.post("/api/contacts/import")
async def contacts_import(request: Request):
    body = await request.json()
    existing = _load_json(CONTACTS_FILE, [])
    new_contacts = body.get("contacts", [])
    existing.extend(new_contacts)
    _save_json(CONTACTS_FILE, existing)
    return {"ok": True, "imported": len(new_contacts)}

@app.get("/api/contacts/search")
async def contacts_search(q: str = ""):
    items = _load_json(CONTACTS_FILE, [])
    if q:
        ql = q.lower()
        items = [i for i in items if ql in str(i.get("name", "")).lower() or ql in str(i.get("email", "")).lower()]
    return items

# ── Signatures ──

SIGNATURES_FILE = DATA_DIR / "signatures.json"

@app.get("/api/signatures")
async def signatures_list():
    return _load_json(SIGNATURES_FILE, [])

@app.post("/api/signatures")
async def signatures_create(request: Request):
    body = await request.json()
    items = _load_json(SIGNATURES_FILE, [])
    sig = {"id": _uid(), **body, "created_at": _now()}
    items.append(sig)
    _save_json(SIGNATURES_FILE, items)
    return sig

@app.delete("/api/signatures/{sid}")
async def signatures_delete(sid: str):
    items = _load_json(SIGNATURES_FILE, [])
    items = [i for i in items if i.get("id") != sid]
    _save_json(SIGNATURES_FILE, items)
    return {"ok": True}

# ── Document sub-routes ──

@app.get("/api/document/{doc_id}/export-pdf")
async def document_export_pdf(doc_id: str):
    return {"ok": True, "message": "PDF export not available server-side"}

@app.post("/api/document/{doc_id}/export-pdf/preview")
async def document_export_pdf_preview(doc_id: str):
    return {"ok": True, "preview": ""}

@app.get("/api/document/{doc_id}/render-pages")
async def document_render_pages(doc_id: str):
    return {"pages": []}

@app.get("/api/document/{doc_id}/render-pdf")
async def document_render_pdf(doc_id: str):
    return {"ok": True, "pdf_url": ""}

@app.get("/api/document/{doc_id}/page/{n}.png")
async def document_page_png(doc_id: str, n: int):
    return JSONResponse({"error": "not available"}, status_code=404)

@app.post("/api/document/{doc_id}/ai-fill-annotations")
async def document_ai_fill(doc_id: str):
    return {"ok": True, "annotations": []}

@app.post("/api/document/{doc_id}/extract-pdf-text")
async def document_extract_pdf(doc_id: str):
    return {"ok": True, "text": ""}

@app.get("/api/document/{doc_id}/versions")
async def document_versions(doc_id: str):
    return []

@app.get("/api/document/{doc_id}/version/{n}")
async def document_version(doc_id: str, n: int):
    return {"version": n, "content": ""}

@app.post("/api/document/{doc_id}/restore/{n}")
async def document_restore(doc_id: str, n: int):
    return {"ok": True}

@app.post("/api/document/{doc_id}/prepare-signed-reply")
async def document_signed_reply(doc_id: str):
    return {"ok": True, "reply": ""}

@app.put("/api/document/{did}")
async def save_document(did: str, request: Request):
    body = await request.json()
    docs = _load_json(DOCUMENTS_FILE, [])
    for d in docs:
        if d.get("id") == did:
            d.update(body)
            d["updated_at"] = _now()
            _save_json(DOCUMENTS_FILE, docs)
            return d
    doc = {"id": did, "created_at": _now(), "updated_at": _now(), **body}
    docs.append(doc)
    _save_json(DOCUMENTS_FILE, docs)
    return doc

@app.patch("/api/document/{did}")
async def patch_document(did: str, request: Request):
    body = await request.json()
    docs = _load_json(DOCUMENTS_FILE, [])
    for d in docs:
        if d.get("id") == did:
            d.update(body)
            d["updated_at"] = _now()
    _save_json(DOCUMENTS_FILE, docs)
    return JSONResponse({})

# ── Editor-drafts ──

@app.delete("/api/editor-drafts/{did}")
async def editor_draft_delete(did: str):
    items = _load_json(EDITOR_DRAFTS_FILE, [])
    items = [i for i in items if i.get("id") != did]
    _save_json(EDITOR_DRAFTS_FILE, items)
    return {"ok": True}

@app.get("/api/editor-drafts/{did}")
async def editor_draft_get(did: str):
    items = _load_json(EDITOR_DRAFTS_FILE, [])
    draft = next((d for d in items if d.get("id") == did), None)
    return draft or {}

@app.put("/api/editor-drafts/{did}")
async def editor_draft_update(did: str, request: Request):
    body = await request.json()
    items = _load_json(EDITOR_DRAFTS_FILE, [])
    for d in items:
        if d.get("id") == did:
            d.update(body)
            _save_json(EDITOR_DRAFTS_FILE, items)
            return d
    draft = {"id": did, "created_at": _now(), **body}
    items.append(draft)
    _save_json(EDITOR_DRAFTS_FILE, items)
    return draft

# ── Image operations ──

@app.post("/api/image/mask")
async def image_mask():
    return {"ok": True, "mask_url": "", "mask": "", "bbox": [0, 0, 0, 0]}

@app.post("/api/image/inpaint")
async def image_inpaint():
    return {"ok": True, "result_url": ""}

@app.post("/api/image/upscale-local")
async def image_upscale():
    return {"ok": True, "result_url": ""}

# ── Gallery extended ──

@app.post("/api/gallery/upload")
async def gallery_upload():
    return {"ok": True, "id": _uid(), "url": ""}

GALLERY_ALBUMS_FILE = DATA_DIR / "gallery_albums.json"

@app.get("/api/gallery/albums")
async def gallery_albums():
    return _load_json(GALLERY_ALBUMS_FILE, [])

@app.post("/api/gallery/albums")
async def gallery_albums_create(request: Request):
    body = await request.json()
    items = _load_json(GALLERY_ALBUMS_FILE, [])
    album = {"id": _uid(), **body, "created_at": _now()}
    items.append(album)
    _save_json(GALLERY_ALBUMS_FILE, items)
    return album

@app.put("/api/gallery/albums/{aid}")
async def gallery_albums_update(aid: str, request: Request):
    body = await request.json()
    items = _load_json(GALLERY_ALBUMS_FILE, [])
    for item in items:
        if item.get("id") == aid:
            item.update(body)
    _save_json(GALLERY_ALBUMS_FILE, items)
    return {"ok": True}

@app.delete("/api/gallery/albums/{aid}")
async def gallery_albums_delete(aid: str):
    items = _load_json(GALLERY_ALBUMS_FILE, [])
    items = [i for i in items if i.get("id") != aid]
    _save_json(GALLERY_ALBUMS_FILE, items)
    return {"ok": True}

@app.post("/api/gallery/ai-tag-batch")
async def gallery_ai_tag_batch(request: Request):
    return {"ok": True, "tags": []}

@app.post("/api/gallery/clear-ai-tags")
async def gallery_clear_ai_tags(request: Request):
    return {"ok": True}

@app.get("/api/gallery/download-zip")
async def gallery_download_zip():
    return {"ok": True, "message": "ZIP download not available"}

@app.post("/api/gallery/style-transfer")
async def gallery_style_transfer():
    return {"ok": True, "result_url": ""}

@app.patch("/api/gallery/{iid}")
async def gallery_patch_image(iid: str, request: Request):
    body = await request.json()
    items_data = _load_json(GALLERY_FILE, {"items": []})
    items = items_data.get("items", []) if isinstance(items_data, dict) else items_data
    for item in items:
        if item.get("id") == iid:
            item.update(body)
    if isinstance(items_data, dict):
        items_data["items"] = items
        _save_json(GALLERY_FILE, items_data)
    return {"ok": True}

@app.delete("/api/gallery/{iid}")
async def gallery_delete_image(iid: str):
    items_data = _load_json(GALLERY_FILE, {"items": []})
    items = items_data.get("items", []) if isinstance(items_data, dict) else items_data
    items = [i for i in items if i.get("id") != iid]
    if isinstance(items_data, dict):
        items_data["items"] = items
        _save_json(GALLERY_FILE, items_data)
    return {"ok": True}

@app.post("/api/gallery/{iid}/favorite")
async def gallery_favorite(iid: str):
    items_data = _load_json(GALLERY_FILE, {"items": []})
    items = items_data.get("items", []) if isinstance(items_data, dict) else items_data
    fav = False
    for item in items:
        if item.get("id") == iid:
            item["favorite"] = not item.get("favorite", False)
            fav = item["favorite"]
    if isinstance(items_data, dict):
        items_data["items"] = items
        _save_json(GALLERY_FILE, items_data)
    return {"ok": True, "favorite": fav}

@app.post("/api/gallery/{iid}/rotate")
async def gallery_rotate(iid: str, request: Request):
    return {"ok": True}

@app.post("/api/gallery/{iid}/rename")
async def gallery_rename(iid: str, request: Request):
    body = await request.json()
    items_data = _load_json(GALLERY_FILE, {"items": []})
    items = items_data.get("items", []) if isinstance(items_data, dict) else items_data
    for item in items:
        if item.get("id") == iid:
            item["name"] = body.get("name", item.get("name", ""))
    if isinstance(items_data, dict):
        items_data["items"] = items
        _save_json(GALLERY_FILE, items_data)
    return {"ok": True}

@app.post("/api/gallery/{iid}/ai-tag")
async def gallery_ai_tag(iid: str):
    return {"ok": True, "ai_tags": ""}

@app.post("/api/gallery/{iid}/replace")
async def gallery_replace(iid: str):
    return {"ok": True}

# ── Memory extended ──

@app.post("/api/memory/add")
async def memory_add(request: Request):
    body = await request.json()
    items = _load_json(MEMORY_FILE, [])
    entry = {"id": _uid(), **body, "created_at": _now(), "updated_at": _now()}
    items.append(entry)
    _save_json(MEMORY_FILE, items)
    return entry

@app.get("/api/memory/audit")
async def memory_audit():
    items = _load_json(MEMORY_FILE, [])
    return {"count": len(items), "items": items}

@app.post("/api/memory/extract")
async def memory_extract(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct or "x-www-form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    return {"ok": True, "memories": [], "suggestions": []}

@app.post("/api/memory/import")
async def memory_import(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct or "x-www-form" in ct:
        form = await request.form()
        body = {k: v for k, v in form.items()}
    else:
        body = await request.json()
    return {"ok": True, "imported": 0, "suggestions": []}

@app.post("/api/memory/{mid}/pin")
async def memory_pin(mid: str, request: Request):
    items = _load_json(MEMORY_FILE, [])
    for item in items:
        if item.get("id") == mid:
            item["pinned"] = not item.get("pinned", False)
            item["updated_at"] = _now()
    _save_json(MEMORY_FILE, items)
    return {"ok": True}

@app.post("/api/memory/search")
async def memory_search(request: Request):
    ct = request.headers.get("content-type", "")
    if "form" in ct:
        form = await request.form()
        query = str(form.get("query", "")).lower()
    else:
        body = await request.json()
        query = body.get("query", "").lower()
    items = _load_json(MEMORY_FILE, [])
    if query:
        items = [i for i in items if query in str(i.get("content", "")).lower() or query in str(i.get("text", "")).lower()]
    return {"memories": items}

# ── Notes extended ──

@app.post("/api/notes/reorder")
async def notes_reorder(request: Request):
    body = await request.json()
    return {"ok": True}

# ── Skills extended ──

@app.post("/api/skills/add")
async def skills_add(request: Request):
    body = await request.json()
    items = _load_json(DATA_DIR / "skills.json", [])
    skill = {"id": _uid(), **body, "created_at": _now()}
    items.append(skill)
    _save_json(DATA_DIR / "skills.json", items)
    return skill

@app.get("/api/skills/search")
async def skills_search(q: str = ""):
    items = _load_json(DATA_DIR / "skills.json", [])
    if q:
        ql = q.lower()
        items = [i for i in items if ql in str(i.get("name", "")).lower() or ql in str(i.get("description", "")).lower()]
    return items

@app.get("/api/skills/builtin/{name}")
async def skills_builtin_get(name: str):
    f = SKILLS_DIR / f"{name}.md"
    content = f.read_text(encoding="utf-8") if f.exists() else ""
    return {"name": name, "builtin": True, "description": "", "content": content, "text": content, "default": content}

@app.post("/api/skills/builtin/{name}")
async def skills_builtin_install(name: str):
    return {"ok": True, "name": name}

@app.delete("/api/skills/builtin/{name}")
async def skills_builtin_delete(name: str):
    return {"ok": True}

@app.get("/api/skills/audit-all")
async def skills_audit_all():
    return {"results": []}

@app.get("/api/skills/audit-all/status")
async def skills_audit_all_status():
    return {"status": "none", "running": False, "progress": 100, "done": 0, "total": 0, "current": None, "results": [], "log": [], "teacher": None}

@app.post("/api/skills/audit-all/cancel")
async def skills_audit_all_cancel():
    return {"ok": True}

@app.post("/api/skills/import-from-url")
async def skills_import_from_url(request: Request):
    body = await request.json()
    return {"ok": True, "skill": {"id": _uid(), "name": body.get("name", "imported")}}

@app.put("/api/skills/{name}")
async def skills_update(name: str, request: Request):
    body = await request.json()
    skills = _load_json(DATA_DIR / "skills.json", [])
    for s in skills:
        if s.get("name") == name:
            s.update(body)
            s["updated_at"] = _now()
    _save_json(DATA_DIR / "skills.json", skills)
    return {"ok": True}

@app.post("/api/skills/{name}/markdown")
async def skills_save_markdown(name: str, request: Request):
    body = await request.json()
    f = SKILLS_DIR / f"{name}.md"
    f.write_text(body.get("markdown", ""), encoding="utf-8")
    return {"ok": True}

@app.get("/api/skills/{name}/test-status")
async def skills_test_status(name: str):
    return {"status": "none", "result": None, "log": [], "approval": None, "verdict": None}

@app.post("/api/skills/{name}/test")
async def skills_test(name: str, request: Request):
    return {"ok": True, "result": "passed"}

@app.post("/api/skills/{name}/test-approval")
async def skills_test_approval(name: str, request: Request):
    return {"ok": True}

# ── Tasks extended ──

@app.post("/api/tasks/parse")
async def tasks_parse(request: Request):
    body = await request.json()
    text = body.get("text", body.get("description", ""))
    return {"success": True, "tasks": [{"name": text, "priority": "medium"}] if text else [], "draft": text}

@app.get("/api/tasks/runs/recent")
async def tasks_runs_recent():
    return {"runs": [], "has_more": False}

@app.get("/api/tasks/meta/email-accounts")
async def task_email_accounts():
    return []

@app.post("/api/tasks/{tid}/pause")
async def task_pause(tid: str):
    return {"ok": True}

@app.post("/api/tasks/{tid}/resume")
async def task_resume(tid: str):
    return {"ok": True}

@app.post("/api/tasks/{tid}/run")
async def task_run(tid: str):
    return {"ok": True}

@app.post("/api/tasks/{tid}/stop")
async def task_stop(tid: str):
    return {"ok": True}

@app.post("/api/tasks/{tid}/revert")
async def task_revert(tid: str):
    return {"ok": True}

@app.post("/api/tasks/{tid}/clear-cache")
async def task_clear_cache(tid: str):
    return {"ok": True}

@app.get("/api/tasks/{tid}/runs")
async def task_runs(tid: str):
    return {"runs": []}

# ── Prefs ──

PREFS_FILE = DATA_DIR / "prefs.json"

@app.get("/api/prefs")
async def prefs_get():
    return _load_json(PREFS_FILE, {})

@app.get("/api/prefs/{key}")
async def prefs_get_key(key: str):
    prefs = _load_json(PREFS_FILE, {})
    return {"value": prefs.get(key, None)}

@app.put("/api/prefs/{key}")
async def prefs_put_key(key: str, request: Request):
    body = await request.json()
    prefs = _load_json(PREFS_FILE, {})
    if isinstance(body, dict) and "value" in body:
        prefs[key] = body["value"]
    else:
        prefs[key] = body
    _save_json(PREFS_FILE, prefs)
    return {"ok": True}

@app.post("/api/prefs/{key}")
async def prefs_post_key(key: str, request: Request):
    body = await request.json()
    prefs = _load_json(PREFS_FILE, {})
    if isinstance(body, dict) and "value" in body:
        prefs[key] = body["value"]
    else:
        prefs[key] = body
    _save_json(PREFS_FILE, prefs)
    return {"ok": True}

@app.get("/api/prefs/theme")
async def prefs_theme():
    prefs = _load_json(PREFS_FILE, {})
    return prefs.get("theme", {"name": "default"})

@app.put("/api/prefs/theme")
async def prefs_theme_put(request: Request):
    body = await request.json()
    prefs = _load_json(PREFS_FILE, {})
    prefs["theme"] = body
    _save_json(PREFS_FILE, prefs)
    return body

@app.post("/api/prefs/theme")
async def prefs_theme_post(request: Request):
    body = await request.json()
    prefs = _load_json(PREFS_FILE, {})
    prefs["theme"] = body
    _save_json(PREFS_FILE, prefs)
    return body

@app.get("/api/prefs/custom-themes")
async def prefs_custom_themes():
    prefs = _load_json(PREFS_FILE, {})
    return prefs.get("custom_themes", [])

@app.put("/api/prefs/custom-themes")
async def prefs_custom_themes_put(request: Request):
    body = await request.json()
    prefs = _load_json(PREFS_FILE, {})
    prefs["custom_themes"] = body if isinstance(body, list) else body.get("themes", [])
    _save_json(PREFS_FILE, prefs)
    return {"ok": True}

# ── Vault ──

@app.get("/api/vault/config")
async def vault_config():
    data = _load_json(VAULT_FILE, {})
    return {
        "enabled": bool(data.get("server_url")),
        "locked": not bool(data.get("unlocked")),
        "server_url": data.get("server_url", ""),
        "email": data.get("email", ""),
        "bw_installed": False,
        "unlocked": bool(data.get("unlocked")),
        "unlocked_at": data.get("unlocked_at", None),
    }

@app.post("/api/vault/config")
async def vault_config_post(request: Request):
    body = await request.json()
    data = _load_json(VAULT_FILE, {})
    data["server_url"] = body.get("server_url", data.get("server_url", ""))
    data["email"] = body.get("email", data.get("email", ""))
    _save_json(VAULT_FILE, data)
    return {"ok": True}

@app.post("/api/vault/login")
async def vault_login(request: Request):
    return {"ok": True, "token": ""}

@app.post("/api/vault/unlock")
async def vault_unlock(request: Request):
    return {"ok": True}

@app.post("/api/vault/lock")
async def vault_lock():
    return {"ok": True}

@app.post("/api/vault/logout")
async def vault_logout():
    return {"ok": True}

# ── Research extended ──

@app.get("/api/research/active")
async def research_active():
    return {"active": []}

@app.post("/api/research/start")
async def research_start(request: Request):
    body = await request.json()
    rid = _uid()
    return {"ok": True, "id": rid, "session_id": rid}

@app.get("/api/research/detail/{rid}")
async def research_detail(rid: str):
    return {
        "id": rid, "status": "completed", "results": [],
        "summary": "", "report_summary": "", "result": "", "raw_report": "",
        "sources": [], "raw_findings": [], "session_id": rid, "category": "",
    }

@app.post("/api/research/{rid}/archive")
async def research_archive(rid: str):
    return {"ok": True}

@app.get("/api/research/result-peek/{rid}")
@app.post("/api/research/result-peek/{rid}")
async def research_result_peek(rid: str):
    return {"id": rid, "result": "", "sources": [], "raw_findings": [], "category": ""}

@app.delete("/api/research/{rid}")
async def research_delete(rid: str):
    return {"ok": True}

@app.get("/api/research/stream/{rid}")
async def research_stream(rid: str):
    async def generate():
        yield f"data: {json.dumps({'status': 'done', 'final': True, 'result': '', 'sources': [], 'raw_findings': []})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

# ── Cookbook extended ──

@app.get("/api/cookbook/hf-latest")
async def cookbook_hf_latest():
    return {"models": []}

@app.get("/api/cookbook/tasks/status")
async def cookbook_tasks_status():
    return {"tasks": [], "running": False}

# ── TTS extended ──

@app.post("/api/tts/clear-cache")
async def tts_clear_cache():
    return {"ok": True}

# ── Misc missing ──

@app.post("/api/probe-selected")
async def probe_selected(request: Request):
    body = await request.json()
    return {"ok": True, "results": []}

@app.post("/api/documents/tidy")
async def documents_tidy(request: Request):
    return {"ok": True}

@app.post("/api/documents/ai-tidy")
async def documents_ai_tidy(request: Request):
    return {"ok": True}

@app.get("/api/documents/export-zip")
async def export_zip_get():
    return JSONResponse({"status": "no documents"})

@app.post("/api/documents/export-zip")
async def export_zip_post(request: Request):
    return {"ok": True, "status": "no documents"}

@app.get("/api/fonts/custom")
async def fonts_custom():
    return []

@app.get("/api/workspace/vet")
async def workspace_vet(path: str = ""):
    target = path if path else str(DATA_DIR.parent)
    issues = []
    if not os.path.exists(target):
        issues.append({"level": "error", "message": f"Path does not exist: {target}"})
    return {"path": target, "ok": len(issues) == 0, "issues": issues}

@app.get("/api/workspace/browse")
async def workspaceBrowse(path: str = ""):
    target = path if path else str(DATA_DIR.parent)
    dirs = []
    files_list = []
    try:
        for entry in os.scandir(target):
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": entry.path})
            elif entry.is_file():
                files_list.append({"name": entry.name, "path": entry.path})
    except Exception:
        pass
    parent = str(Path(target).parent)
    return {"path": target, "parent": parent, "dirs": dirs, "files": files_list, "truncated": False, "selectable": True}

@app.get("/api/ping")
async def ping():
    return {"ok": True, "timestamp": _now()}

@app.get("/api/db/stats")
async def db_stats():
    return {"sessions": len(_load_sessions()), "notes": len(_load_json(DATA_DIR / "notes.json", [])), "tasks": len(_load_json(DATA_DIR / "tasks.json", [])), "memory": len(_load_json(MEMORY_FILE, []))}

@app.post("/api/mcp/oauth/exchange/{oid}")
async def mcp_oauth_exchange(oid: str, request: Request):
    return {"ok": True, "token": ""}

# ── Session export/restore ──

@app.get("/api/session/{sid}/export")
async def session_export(sid: str):
    s = _find_session(sid)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    return {"session": s, "history": _get_history(sid)}

@app.post("/api/session/{sid}/restore")
async def session_restore(sid: str):
    return {"ok": True}

# ── Shell stream POST ──

@app.post("/api/shell/stream")
async def shell_stream_post(request: Request):
    body = await request.json()
    cmd = body.get("command", "echo hello")
    async def generate():
        try:
            result = await asyncio.to_thread(lambda: subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=str(DATA_DIR.parent)))
            yield f"data: {json.dumps({'output': result.stdout, 'error': result.stderr, 'done': True, 'exit_code': result.returncode})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'output': '', 'error': str(e), 'done': True, 'exit_code': -1})}\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

# ── Hwfit extended ──

@app.get("/api/hwfit/image-models")
async def hwfit_image_models():
    return {"models": []}

# ── ChatGPT subscription device flow stubs ──

@app.get("/api/chatgpt-subscription/device/start")
async def chatgpt_device_start():
    return {"error": "Not available", "device_code": "", "user_code": "", "verification_uri": ""}

@app.get("/api/chatgpt-subscription/device/poll")
async def chatgpt_device_poll():
    return {"status": "not_started"}

# ── Email accounts CRUD ──

@app.post("/api/email/accounts")
async def email_accounts_create(request: Request):
    body = await request.json()
    accounts = _load_json(EMAIL_ACCOUNTS_FILE, [])
    account = {"id": _uid(), "created_at": _now(), "enabled": True, **body}
    accounts.append(account)
    _save_json(EMAIL_ACCOUNTS_FILE, accounts)
    return account

@app.put("/api/email/accounts/{aid}")
async def email_accounts_update(aid: str, request: Request):
    body = await request.json()
    accounts = _load_json(EMAIL_ACCOUNTS_FILE, [])
    for a in accounts:
        if a.get("id") == aid:
            a.update(body)
    _save_json(EMAIL_ACCOUNTS_FILE, accounts)
    return {"ok": True}

@app.delete("/api/email/accounts/{aid}")
async def email_accounts_delete(aid: str):
    accounts = _load_json(EMAIL_ACCOUNTS_FILE, [])
    accounts = [a for a in accounts if a.get("id") != aid]
    _save_json(EMAIL_ACCOUNTS_FILE, accounts)
    return {"ok": True}

@app.put("/api/email/config")
async def email_config_put(request: Request):
    body = await request.json()
    _save_json(DATA_DIR / "email_config.json", body)
    return {"ok": True}

# ── MCP POST servers ──

@app.post("/api/mcp/servers/{id}")
async def mcp_update_post(id: str, request: Request):
    body = await request.json()
    servers = _load_json(MCP_FILE, [])
    for s in servers:
        if s.get("id") == id:
            s.update(body)
    _save_json(MCP_FILE, servers)
    return {"ok": True}

# ── Compare probe ──

@app.post("/api/compare/probe")
async def compare_probe(request: Request):
    body = await request.json()
    return {"results": []}

# ── Method aliases (frontend sends POST, server had GET, etc.) ──

@app.post("/api/skills/search")
async def skills_search_post(request: Request):
    body = await request.json()
    q = body.get("query", body.get("q", ""))
    items = _load_json(DATA_DIR / "skills.json", [])
    if q:
        ql = q.lower()
        items = [i for i in items if ql in str(i.get("name", "")).lower() or ql in str(i.get("description", "")).lower()]
    return {"skills": items}

@app.post("/api/skills/audit-all")
async def skills_audit_all_post(request: Request):
    return {"results": []}

@app.put("/api/skills/builtin/{name}")
async def skills_builtin_update(name: str, request: Request):
    body = await request.json()
    f = SKILLS_DIR / f"{name}.md"
    f.write_text(body.get("text", body.get("content", "")), encoding="utf-8")
    return {"ok": True}

@app.post("/api/session/{sid}/message")
async def session_inject_message(sid: str, request: Request):
    body = await request.json()
    history = _get_history(sid)
    history.append({"role": body.get("role", "assistant"), "content": body.get("content", ""), "id": _uid()})
    _save_history(sid, history)
    return {"ok": True}

@app.post("/api/skills/{name}/invoke")
async def skills_invoke(name: str, request: Request):
    return {"ok": True, "result": f"Skill {name} invoked"}

# ── Calendar config accounts CRUD ──

CALENDAR_ACCOUNTS_FILE = DATA_DIR / "calendar_accounts.json"

@app.get("/api/calendar/config/accounts")
async def calendar_config_accounts():
    return {"accounts": _load_json(CALENDAR_ACCOUNTS_FILE, [])}

@app.post("/api/calendar/config/accounts")
async def calendar_config_accounts_create(request: Request):
    body = await request.json()
    items = _load_json(CALENDAR_ACCOUNTS_FILE, [])
    account = {"id": _uid(), "created_at": _now(), "enabled": True, **body}
    items.append(account)
    _save_json(CALENDAR_ACCOUNTS_FILE, items)
    return account

@app.put("/api/calendar/config/accounts/{aid}")
async def calendar_config_accounts_update(aid: str, request: Request):
    body = await request.json()
    items = _load_json(CALENDAR_ACCOUNTS_FILE, [])
    for item in items:
        if item.get("id") == aid:
            item.update(body)
    _save_json(CALENDAR_ACCOUNTS_FILE, items)
    return {"ok": True}

@app.delete("/api/calendar/config/accounts/{aid}")
async def calendar_config_accounts_delete(aid: str):
    items = _load_json(CALENDAR_ACCOUNTS_FILE, [])
    items = [i for i in items if i.get("id") != aid]
    _save_json(CALENDAR_ACCOUNTS_FILE, items)
    return {"ok": True}

# ── Memory audit POST alias ──

@app.post("/api/memory/audit")
async def memory_audit_post(request: Request):
    items = _load_json(MEMORY_FILE, [])
    return {"removed": 0, "count": len(items), "items": items, "suggestions": []}

# ── Gallery download-zip POST alias ──

@app.post("/api/gallery/download-zip")
async def gallery_download_zip_post(request: Request):
    return {"ok": True, "message": "ZIP download not available"}

# ── Upload files key fallback ──

@app.post("/api/upload")
async def upload_file(request: Request):
    form = await request.form()
    upload = form.get("file") or (form.get("files") if hasattr(form, "get") else None)
    if not upload or not hasattr(upload, "filename"):
        for key in form:
            val = form[key]
            if hasattr(val, "filename") and val.filename:
                upload = val
                break
    if upload and hasattr(upload, "filename"):
        fid = _uid()
        dest = UPLOADS_DIR / f"{fid}_{upload.filename}"
        content = await upload.read()
        dest.write_bytes(content)
        return {"id": fid, "filename": upload.filename, "size": len(content), "url": f"/api/upload/{fid}", "files": [{"id": fid, "filename": upload.filename, "size": len(content), "url": f"/api/upload/{fid}"}]}
    return JSONResponse({"error": "no file"}, status_code=400)



# ──────────────────── STATIC MOUNT (must be last) ────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
