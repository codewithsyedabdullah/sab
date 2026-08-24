from __future__ import annotations

import json
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .agent import Agent
from .config import Config

app = FastAPI(title="SAB Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS_DIR = Path.home() / ".sab" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

sessions: dict[str, Agent] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    model: str = "codellama:13b"
    provider: str = "ollama"
    api_key: str = ""


class SessionConfig(BaseModel):
    model: str = "codellama:13b"
    provider: str = "ollama"
    api_key: str = ""
    workspace: str = str(Path.cwd())


def get_or_create_agent(session_id: str, config: SessionConfig | None = None) -> tuple[str, Agent]:
    if not session_id:
        session_id = str(uuid.uuid4())

    if session_id not in sessions:
        cfg = Config.from_env()
        if config:
            cfg.llm.model = config.model
            cfg.llm.provider = config.provider
            if config.api_key:
                cfg.llm.api_key = config.api_key
            cfg.workspace = Path(config.workspace)

        agent = Agent(cfg)
        session_path = SESSIONS_DIR / session_id
        agent.load_session(str(session_path))
        sessions[session_id] = agent

    return session_id, sessions[session_id]


@app.post("/api/chat")
async def chat(request: ChatRequest):
    session_id, agent = get_or_create_agent(
        request.session_id,
        SessionConfig(model=request.model, provider=request.provider, api_key=request.api_key),
    )

    response = agent.run(request.message)

    agent.save_session(str(SESSIONS_DIR / session_id))

    return JSONResponse({
        "response": response,
        "session_id": session_id,
    })


@app.post("/api/session/new")
async def new_session():
    session_id = str(uuid.uuid4())
    return JSONResponse({"session_id": session_id})


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
    session_path = SESSIONS_DIR / session_id
    if session_path.exists():
        import shutil
        shutil.rmtree(session_path)
    return JSONResponse({"status": "deleted"})


@app.get("/api/sessions")
async def list_sessions():
    session_dirs = [d.name for d in SESSIONS_DIR.iterdir() if d.is_dir()] if SESSIONS_DIR.exists() else []
    return JSONResponse({"sessions": session_dirs})


@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()

    session_id = ""
    agent = None

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "config":
                session_id, agent = get_or_create_agent(
                    msg.get("session_id", ""),
                    SessionConfig(
                        model=msg.get("model", "codellama:13b"),
                        provider=msg.get("provider", "ollama"),
                        api_key=msg.get("api_key", ""),
                        workspace=msg.get("workspace", str(Path.cwd())),
                    ),
                )
                await websocket.send_text(json.dumps({"type": "session", "session_id": session_id}))
                continue

            if msg.get("type") == "chat":
                if not agent:
                    session_id, agent = get_or_create_agent("")

                user_message = msg.get("message", "")
                if not user_message:
                    continue

                for event in agent.run_stream(user_message):
                    await websocket.send_text(json.dumps(event))

                agent.save_session(str(SESSIONS_DIR / session_id))
                continue

            if msg.get("type") == "reset":
                if agent:
                    agent.reset()
                continue

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass


def start_server(host: str = "0.0.0.0", port: int = 3000):
    uvicorn.run(app, host=host, port=port)
