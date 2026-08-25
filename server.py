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
from datetime import datetime, timezone
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
    return {"authenticated": True, "user": {"username": "sab", "is_admin": True, "display_name": "SAB"}}


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
    return [{"username": "sab", "is_admin": True, "display_name": "SAB"}]


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
async def auth_set_privileges(username: str, request: Request):
    return JSONResponse({})


@app.post("/api/auth/users/{username}/rename")
async def auth_rename_user(username: str, request: Request):
    return JSONResponse({})


@app.post("/api/auth/users/{username}/admin")
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
        r = _req.get("http://localhost:11434/api/tags", timeout=3)
        if r.ok:
            data = r.json().get("models", [])
            return {"items": [{"id": "sab-local", "name": "Ollama Local", "models": [{"id": m["name"], "name": m["name"], "provider": "ollama"} for m in data]}]}
    except Exception:
        pass
    return {"items": [{"id": "sab-local", "name": "SAB Local", "models": [{"id": config.llm.model, "name": config.llm.model, "provider": config.llm.provider}]}]}


@app.get("/api/providers")
async def providers():
    return {"providers": [{"id": "sab-local", "name": "SAB Local", "models": [config.llm.model]}]}


@app.get("/api/model-endpoints")
async def model_endpoints():
    endpoints = _load_json(DATA_DIR / "model_endpoints.json", [])
    if not endpoints:
        endpoints = [{"id": "sab-local", "base_url": "http://localhost:11434", "models": [{"id": config.llm.model, "name": config.llm.model}], "pinned_models": [], "offline": False}]
    return endpoints


@app.post("/api/model-endpoints")
async def create_model_endpoint(request: Request):
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
        r = _req.get("http://localhost:11434/api/tags", timeout=3)
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
    return [s for s in _load_sessions() if s.get("archived", False)][:limit]


@app.post("/api/sessions/auto-sort")
async def auto_sort(request: Request):
    return JSONResponse({})


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
    return JSONResponse({"status": "ok"})


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
    return {"system_prompt": "You are SAB.", "messages": _get_history(sid)}


@app.get("/api/session/{sid}/context_info")
async def session_context_info(sid: str):
    history = _get_history(sid)
    return {"total_messages": len(history), "estimated_tokens": sum(len(m.get("content", "")) // 4 for m in history)}


# ──────────────────── HISTORY ────────────────────

@app.get("/api/history/{sid}")
async def get_history(sid: str, limit: int = 100, offset: int = 0):
    history = _get_history(sid)
    total = len(history)
    sliced = history[offset:offset + limit]
    return {"history": sliced, "offset": offset, "total": total, "has_more_before": offset > 0, "has_more_after": offset + limit < total}


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

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"})


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
    text = body.get("text", "")
    name = text[:40] if text else "New Chat"
    return {"name": name}


@app.get("/api/ai/name")
async def ai_name():
    return {"name": "SAB"}


# ──────────────────── PRESETS ────────────────────

@app.get("/api/presets")
async def presets():
    data = _load_json(PRESETS_FILE, {})
    if not data:
        data = {"default": {"name": "SAB", "character_name": "SAB", "system_prompt": "You are SAB."}}
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
    return []


@app.post("/api/presets/expand")
async def preset_expand(request: Request):
    body = await request.json()
    return {"prompt": body.get("prompt", "")}


@app.get("/api/presets/groups")
async def preset_groups():
    return []


# ──────────────────── MEMORY ────────────────────

@app.get("/api/memory")
async def memory_list():
    return _load_json(MEMORY_FILE, [])


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
    return JSONResponse({})


# ──────────────────── TASKS ────────────────────

@app.get("/api/tasks")
async def tasks_list():
    return _load_json(TASKS_FILE, [])


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
    return {"completed": True}


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
    return _load_json(DATA_DIR / "skills.json", [])


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
    return docs


@app.get("/api/documents/import-pdf")
async def import_pdf_get():
    return JSONResponse({"error": "Use POST"}, status_code=400)


@app.post("/api/documents/import-pdf")
async def import_pdf(request: Request):
    return JSONResponse({"status": "imported", "id": _uid()})


@app.get("/api/documents/export-zip")
async def export_zip():
    return JSONResponse({"status": "no documents"})


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

@app.post("/api/upload")
async def upload_file(request: Request):
    form = await request.form()
    upload = form.get("file")
    if upload and hasattr(upload, "filename"):
        fid = _uid()
        dest = UPLOADS_DIR / f"{fid}_{upload.filename}"
        content = await upload.read()
        dest.write_bytes(content)
        return {"id": fid, "filename": upload.filename, "size": len(content), "url": f"/api/upload/{fid}"}
    return JSONResponse({"error": "no file"}, status_code=400)


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
    return data.get("calendars", []) if isinstance(data, dict) else []


@app.post("/api/calendar/calendars")
async def create_calendar(request: Request):
    body = await request.json()
    data = _load_json(CALENDAR_FILE, {"calendars": [], "events": []})
    cal = {"id": _uid(), "name": body.get("name", "Calendar"), "color": body.get("color", "#4a9eff"), "created_at": _now()}
    data.setdefault("calendars", []).append(cal)
    _save_json(CALENDAR_FILE, data)
    return cal


@app.put("/api/calendar/calendars/{cid}")
async def update_calendar(cid: str, request: Request):
    body = await request.json()
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
    return data.get("events", []) if isinstance(data, dict) else []


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
    return {"event": {"title": body.get("text", ""), "start": _now(), "end": _now()}}


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
    return JSONResponse({"status": "imported"})


@app.get("/api/calendar/export/{cid}")
async def calendar_export(cid: str):
    return Response(content="BEGIN:VCALENDAR\nEND:VCALENDAR", media_type="text/calendar")


# ──────────────────── EMAIL ────────────────────

@app.get("/api/email/accounts")
async def email_accounts():
    return _load_json(EMAIL_ACCOUNTS_FILE, [])


@app.post("/api/email/accounts/{id}/set-default")
async def email_set_default(id: str):
    return JSONResponse({})


@app.get("/api/email/config")
async def email_config():
    return {"accounts": []}


@app.get("/api/email/style")
async def email_style():
    return _load_json(EMAIL_STYLE_FILE, {"font_family": "sans-serif", "font_size": "14px"})


@app.post("/api/email/style")
async def email_style_post(request: Request):
    body = await request.json()
    _save_json(EMAIL_STYLE_FILE, body)
    return body


@app.post("/api/email/extract-style")
async def email_extract_style(request: Request):
    return JSONResponse({})


@app.get("/api/email/list")
async def email_list(folder: str = "INBOX", limit: int = 50):
    return []


@app.get("/api/email/folders")
async def email_folders():
    return []


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
    return {"reply": f"AI reply to email {body.get('uid', '')}"}


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
    return {"unread": 0}


@app.get("/api/email/urgency-state")
async def email_urgency_state():
    return {"urgent": 0}


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


@app.post("/api/email/compose-from-sabsabsa")
async def email_compose_from_doc(request: Request):
    return JSONResponse({})


@app.post("/api/email/compose-from-sabsabsa-zip")
async def email_compose_from_doc_zip(request: Request):
    return JSONResponse({})


@app.get("/api/email/inline-image/{uid}")
async def email_inline_image(uid: str):
    return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/email/sabsabsa/reminders")
async def email_reminders():
    return []


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
    return []


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
    gpus = []
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append({"name": parts[0], "vram_total_mb": int(parts[1]), "vram_free_mb": int(parts[2])})
    except Exception:
        pass
    return {"ok": True, "gpus": gpus, "count": len(gpus)}


@app.get("/api/cookbook/state")
async def cookbook_state():
    return _load_json(COOKBOOK_STATE_FILE, {
        "env": {"python": f"{sys.version_info.major}.{sys.version_info.minor}", "platform": sys.platform, "has_gpu": False},
        "tasks": [], "removedTasks": [], "presets": {},
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
    return JSONResponse({"status": "not applicable"})


@app.post("/api/cookbook/rebuild-engine")
async def cookbook_rebuild(request: Request):
    return JSONResponse({"status": "not applicable"})


@app.get("/api/cookbook/hf-gguf-files")
async def cookbook_hf_gguf(repo: str = ""):
    return {"files": []}


@app.post("/api/cookbook/test-ssh")
async def cookbook_test_ssh(request: Request):
    return {"ok": False, "error": "SSH not configured"}


@app.get("/api/cookbook/ssh-key")
async def cookbook_ssh_key():
    return {"key": ""}


@app.post("/api/cookbook/ssh-key")
async def cookbook_gen_ssh_key():
    return {"key": ""}


@app.post("/api/cookbook/setup")
async def cookbook_setup(request: Request):
    return JSONResponse({"status": "not applicable"})


@app.get("/api/cookbook/ollama/library")
async def ollama_library():
    try:
        import requests as _req
        r = _req.get("https://ollama.com/library", timeout=10)
        return {"models": [{"name": "qwen2.5:0.5b", "sizes": ["0.5B"], "description": "Small Qwen model"}]}
    except Exception:
        return {"models": [{"name": "qwen2.5:0.5b", "sizes": ["0.5B"], "description": "Small Qwen model"}]}


# ──────────────────── HWFIT ────────────────────

@app.get("/api/hwfit/system")
async def hwfit_system():
    ram_gb = 0
    try:
        import psutil
        ram_gb = psutil.virtual_memory().total / (1024**3)
    except Exception:
        try:
            result = subprocess.run(["wmic", "memorychip", "get", "Capacity"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line.isdigit():
                        ram_gb += int(line) / (1024**3)
        except Exception:
            ram_gb = 8.0
    return {
        "gpu_count": 0, "detected_gpu_count": 0, "gpu_vram_gb": 0,
        "total_ram_gb": round(ram_gb, 1), "has_gpu": False,
        "platform": sys.platform, "backend": "cpu", "unified_memory": False,
        "gpu_groups": [], "gpu_name": "None",
    }


@app.get("/api/hwfit/profiles")
async def hwfit_profiles():
    return []


@app.get("/api/hwfit/models")
async def hwfit_models():
    return {"system": await hwfit_system(), "models": []}


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
        r = _req.get("http://localhost:11434/api/tags", timeout=3)
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
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=str(DATA_DIR.parent))
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
    body = await request.json()
    return await search(q=body.get("query", body.get("q", "")))


@app.post("/api/search/query")
async def search_query(request: Request):
    body = await request.json()
    return await search(q=body.get("query", body.get("q", "")))


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
    return {"status": "idle"}


@app.post("/api/research/result/{sid}")
async def research_result(sid: str):
    return {"status": "idle", "results": []}


@app.post("/api/research/cancel/{sid}")
async def research_cancel(sid: str):
    return JSONResponse({})


@app.get("/api/research/report/{sid}")
async def research_report(sid: str):
    return {"report": ""}


@app.post("/api/research/spinoff/{sid}")
async def research_spinoff(sid: str):
    return {"session_id": _uid()}


# ──────────────────── TOOLS / MCP ────────────────────

@app.get("/api/mcp/servers")
async def mcp_servers():
    return _load_json(MCP_FILE, [])


@app.post("/api/mcp/servers")
async def mcp_add(request: Request):
    body = await request.json()
    servers = _load_json(MCP_FILE, [])
    server = {"id": _uid(), "enabled": True, **body}
    servers.append(server)
    _save_json(MCP_FILE, servers)
    return server


@app.patch("/api/mcp/servers/{id}")
async def mcp_toggle(id: str, request: Request):
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
    return JSONResponse({})


@app.get("/api/mcp/servers/{id}/tools")
async def mcp_tools(id: str):
    return []


@app.post("/api/mcp/servers/{id}/tools")
async def mcp_tools_post(id: str, request: Request):
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
    return ["UTC", "US/Eastern", "US/Central", "US/Pacific", "Europe/London", "Europe/Berlin", "Asia/Tokyo", "Asia/Karachi", "Asia/Dubai"]


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
    return {"provider": "none", "available": False}


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

@app.get("/api/presets/groups")
async def groups():
    return []


# ──────────────────── PAGE ROUTES ────────────────────

@app.get("/")
async def root():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace("{{CSP_NONCE}}", "")
    return HTMLResponse(html)


@app.get("/login")
async def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))


# ──────────────────── STATIC MOUNT (must be last) ────────────────────

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
