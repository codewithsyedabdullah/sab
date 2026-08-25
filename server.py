from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from sab.config import Config
from sab.agent import Agent

app = FastAPI(title="SAB")

STATIC_DIR = Path(__file__).parent / "static"
DATA_DIR = Path(__file__).parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
SESSION_HISTORIES_DIR = DATA_DIR / "histories"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSION_HISTORIES_DIR.mkdir(parents=True, exist_ok=True)

config = Config.from_env()

active_streams: dict[str, asyncio.Event] = {}
running_agents: dict[str, Agent] = {}


def _load_sessions() -> list[dict]:
    if SESSIONS_FILE.exists():
        try:
            return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_sessions(sessions: list[dict]):
    SESSIONS_FILE.write_text(json.dumps(sessions, indent=2, default=str), encoding="utf-8")


def _get_history(session_id: str) -> list[dict]:
    hfile = SESSION_HISTORIES_DIR / f"{session_id}.json"
    if hfile.exists():
        try:
            return json.loads(hfile.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history(session_id: str, history: list[dict]):
    hfile = SESSION_HISTORIES_DIR / f"{session_id}.json"
    hfile.write_text(json.dumps(history, indent=2, default=str), encoding="utf-8")


def _append_history(session_id: str, role: str, content: str, metadata: dict | None = None):
    history = _get_history(session_id)
    entry: dict[str, Any] = {"role": role, "content": content}
    if metadata:
        entry["metadata"] = metadata
    history.append(entry)
    _save_history(session_id, history)


@app.get("/api/auth/status")
async def auth_status():
    return {"authenticated": True, "user": {"username": "sab", "is_admin": True}}


@app.get("/api/auth/policy")
async def auth_policy():
    return {"signup_enabled": False}


@app.get("/api/auth/features")
async def auth_features():
    return {"signup_enabled": False}


@app.get("/api/version")
async def version():
    return {"version": "0.1.0", "name": "SAB", "codename": "Syed Abdullah Bot"}


@app.get("/api/default-chat")
async def default_chat():
    return {
        "endpoint_url": "local",
        "model": config.llm.model,
        "endpoint_id": "sab-local",
    }


@app.get("/api/models")
async def models():
    return {
        "items": [
            {
                "id": "sab-local",
                "name": "SAB Local",
                "models": [
                    {
                        "id": config.llm.model,
                        "name": config.llm.model,
                        "provider": config.llm.provider,
                    }
                ],
            }
        ]
    }


@app.get("/api/providers")
async def providers():
    return {"providers": [{"id": "sab-local", "name": "SAB Local", "models": [config.llm.model]}]}


@app.get("/api/tools")
async def tools():
    return {"disabled_tools": []}


@app.get("/api/runtime")
async def runtime():
    return {"python": sys.version, "platform": sys.platform, "server": "SAB"}


@app.get("/api/ai/name")
async def ai_name():
    return {"name": "SAB"}


@app.get("/api/presets")
async def presets():
    return {"default": {"name": "SAB", "character_name": "SAB", "system_prompt": "You are SAB."}}


@app.get("/api/presets/templates")
async def preset_templates():
    return []


@app.get("/api/presets/groups")
async def preset_groups():
    return []


@app.get("/api/memory")
async def memory_list():
    return []


@app.get("/api/sessions")
async def list_sessions():
    sessions = _load_sessions()
    sessions.sort(key=lambda s: s.get("updated_at", s.get("created_at", "")), reverse=True)
    return sessions


@app.post("/api/session")
async def create_session(request: Request):
    form = await request.form()
    name = form.get("name", "New Chat")
    model = form.get("model", config.llm.model)
    sid = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat() + "Z"
    session = {
        "id": sid,
        "name": str(name),
        "model": str(model),
        "created_at": now,
        "updated_at": now,
        "important": False,
        "archived": False,
        "folder": None,
        "metadata": {},
    }
    sessions = _load_sessions()
    sessions.append(session)
    _save_sessions(sessions)
    _save_history(sid, [])
    return session


@app.get("/api/session/{sid}")
async def get_session(sid: str):
    sessions = _load_sessions()
    s = next((s for s in sessions if s["id"] == sid), None)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    return s


@app.patch("/api/session/{sid}")
async def update_session(sid: str, request: Request):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    content_type = request.headers.get("content-type", "")
    if "form" in content_type:
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
    s["updated_at"] = datetime.utcnow().isoformat() + "Z"
    _save_sessions(sessions)
    return s


@app.delete("/api/session/{sid}")
async def delete_session(sid: str):
    sessions = _load_sessions()
    sessions = [s for s in sessions if s["id"] != sid]
    _save_sessions(sessions)
    hfile = SESSION_HISTORIES_DIR / f"{sid}.json"
    if hfile.exists():
        hfile.unlink()
    return JSONResponse({})


@app.post("/api/session/{sid}/archive")
async def archive_session(sid: str):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        s["archived"] = True
        s["updated_at"] = datetime.utcnow().isoformat() + "Z"
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/unarchive")
async def unarchive_session(sid: str):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        s["archived"] = False
        s["updated_at"] = datetime.utcnow().isoformat() + "Z"
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/important")
async def toggle_important(sid: str, request: Request):
    sessions = _load_sessions()
    s = next((x for x in sessions if x["id"] == sid), None)
    if s:
        form = await request.form()
        s["important"] = form.get("important", "false") == "true"
        s["updated_at"] = datetime.utcnow().isoformat() + "Z"
        _save_sessions(sessions)
    return JSONResponse({})


@app.post("/api/session/{sid}/compact")
async def compact_session(sid: str):
    return JSONResponse({"status": "ok"})


@app.post("/api/session/{sid}/truncate")
async def truncate_session(sid: str, request: Request):
    body = await request.json()
    keep = body.get("keep_count", 0)
    history = _get_history(sid)
    _save_history(sid, history[:keep])
    return JSONResponse({})


@app.post("/api/session/{sid}/delete-messages")
async def delete_messages(sid: str, request: Request):
    body = await request.json()
    msg_ids = body.get("msg_ids", [])
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
    history = _get_history(sid)[:keep]
    new_sid = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat() + "Z"
    sessions = _load_sessions()
    orig = next((s for s in sessions if s["id"] == sid), None)
    new_session = {
        "id": new_sid,
        "name": (orig.get("name", "Chat") if orig else "Chat") + " (fork)",
        "model": orig.get("model", config.llm.model) if orig else config.llm.model,
        "created_at": now,
        "updated_at": now,
        "important": False,
        "archived": False,
        "folder": None,
        "metadata": {},
    }
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
        history.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    _save_history(sid, history)
    return JSONResponse({})


@app.post("/api/session/{sid}/mark-stopped")
async def mark_stopped(sid: str):
    active_streams.pop(sid, None)
    return JSONResponse({})


@app.get("/api/history/{sid}")
async def get_history(sid: str, limit: int = 100, offset: int = 0):
    history = _get_history(sid)
    total = len(history)
    sliced = history[offset:offset + limit]
    return {
        "history": sliced,
        "offset": offset,
        "total": total,
        "has_more_before": offset > 0,
        "has_more_after": offset + limit < total,
    }


@app.get("/api/chat/stream_status/{sid}")
async def stream_status(sid: str):
    if sid in active_streams:
        return JSONResponse({"status": "streaming"})
    return JSONResponse({"error": "not streaming"}, status_code=404)


@app.post("/api/chat/stop/{sid}")
async def stop_chat(sid: str):
    ev = active_streams.get(sid)
    if ev:
        ev.set()
    return JSONResponse({"status": "stopped"})


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
    session_id = str(form.get("session", ""))
    mode = str(form.get("mode", "chat"))

    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        now = datetime.utcnow().isoformat() + "Z"
        sessions = _load_sessions()
        sessions.append({
            "id": session_id,
            "name": message[:40] if message else "New Chat",
            "model": config.llm.model,
            "created_at": now,
            "updated_at": now,
            "important": False,
            "archived": False,
            "folder": None,
            "metadata": {},
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

            def run_agent():
                events = list(agent.run_stream(message))
                return events

            with concurrent.futures.ThreadPoolExecutor() as pool:
                events = await loop.run_in_executor(pool, run_agent)

            for event in events:
                if stop_event.is_set():
                    break

                if event["type"] == "content":
                    full_response += event["text"]
                    sse_data = json.dumps({"delta": event["text"]})
                    yield f"data: {sse_data}\n\n"

                elif event["type"] == "tool_start":
                    sse_data = json.dumps({
                        "type": "tool_start",
                        "tool": event["name"],
                        "arguments": event.get("arguments", {}),
                    })
                    yield f"data: {sse_data}\n\n"

                elif event["type"] == "tool_result":
                    sse_data = json.dumps({
                        "type": "tool_output",
                        "tool": event["name"],
                        "output": event.get("output", "")[:2000],
                    })
                    yield f"data: {sse_data}\n\n"

                elif event["type"] == "done":
                    pass

            yield "data: [DONE]\n\n"

        except Exception as e:
            err = json.dumps({"status": 500, "message": str(e)})
            yield f"event: error\ndata: {err}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            active_streams.pop(session_id, None)
            running_agents.pop(session_id, None)
            if full_response:
                _append_history(session_id, "assistant", full_response)
                sessions = _load_sessions()
                s = next((x for x in sessions if x["id"] == session_id), None)
                if s:
                    s["updated_at"] = datetime.utcnow().isoformat() + "Z"
                    if s.get("name", "").startswith("New Chat"):
                        s["name"] = message[:40]
                    _save_sessions(sessions)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/search")
async def search(q: str = "", limit: int = 20):
    return []


@app.get("/api/skills")
async def skills():
    return []


@app.get("/api/skills/slash-catalog")
async def slash_catalog():
    return []


@app.get("/api/notes")
async def notes():
    return []


@app.get("/api/tasks")
async def tasks():
    return []


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


@app.get("/api/personal")
async def personal():
    return {"directories": [], "files": []}


@app.get("/api/mcp/servers")
async def mcp_servers():
    return []


@app.get("/api/model-endpoints")
async def model_endpoints():
    return []


@app.get("/api/assistant/settings")
async def assistant_settings():
    return {"crew": [], "check_ins": []}


@app.get("/api/webhooks")
async def webhooks():
    return []


@app.get("/api/tokens")
async def tokens():
    return []


@app.get("/api/tools/config")
async def tools_config():
    return {"disabled_tools": []}


@app.get("/api/gallery/library")
async def gallery():
    return {"items": [], "total": 0}


@app.get("/api/editor-drafts")
async def editor_drafts():
    return []


@app.get("/api/document")
async def document_root():
    return {}


@app.get("/api/calendar/events")
async def calendar_events():
    return []


@app.get("/api/calendar/calendars")
async def calendars():
    return []


@app.get("/api/email/accounts")
async def email_accounts():
    return []


@app.get("/api/diagnostics/logs")
async def diagnostics_logs():
    return []


@app.post("/api/client-perf")
async def client_perf(request: Request):
    return JSONResponse({})


@app.get("/api/activity/heartbeat")
async def heartbeat():
    return JSONResponse({})


@app.post("/api/rewrite")
async def rewrite(request: Request):
    body = await request.json()
    original = body.get("original_text", "")
    instruction = body.get("instruction", "")

    async def generate():
        yield f"data: {json.dumps({'delta': original})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/research/status/{sid}")
async def research_status(sid: str):
    return {"status": "idle"}


@app.get("/api/sessions/archived")
async def archived_sessions(limit: int = 100, sort: str = "recent"):
    sessions = _load_sessions()
    return [s for s in sessions if s.get("archived", False)][:limit]


@app.post("/api/sessions/auto-sort")
async def auto_sort():
    return JSONResponse({})


@app.post("/api/sessions/bulk-delete")
async def bulk_delete(request: Request):
    body = await request.json()
    ids = body.get("session_ids", body.get("ids", []))
    sessions = _load_sessions()
    sessions = [s for s in sessions if s["id"] not in ids]
    _save_sessions(sessions)
    return JSONResponse({})


@app.get("/api/sessions/auto-sort")
async def auto_sort_get():
    sessions = _load_sessions()
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="info")
