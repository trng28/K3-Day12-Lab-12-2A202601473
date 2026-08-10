from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from research_chat import ResearchChatbot


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)


@dataclass
class ChatSession:
    chatbot: ResearchChatbot = field(default_factory=ResearchChatbot)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


SESSIONS: dict[str, ChatSession] = {}
MAX_SESSIONS = 500


def get_session(session_id: str | None) -> tuple[str, ChatSession]:
    resolved = session_id or str(uuid4())
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", resolved):
        raise HTTPException(status_code=400, detail="Invalid session_id")
    if resolved not in SESSIONS:
        if len(SESSIONS) >= MAX_SESSIONS:
            SESSIONS.pop(next(iter(SESSIONS)))
        SESSIONS[resolved] = ChatSession()
    return resolved, SESSIONS[resolved]


def event(event_type: str, **payload: Any) -> bytes:
    return (
        json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"
    ).encode("utf-8")


async def stream_chat(
    session_id: str, session: ChatSession, message: str
) -> AsyncIterator[bytes]:
    yield event("session", session_id=session_id)
    async with session.lock:
        try:
            async for chunk in session.chatbot.respond_stream(message):
                kind = "status" if chunk.lstrip().startswith("[") else "content"
                yield event(kind, content=chunk)
            yield event("done")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            yield event(
                "error",
                error=type(exc).__name__,
                message=str(exc),
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    SESSIONS.clear()


app = FastAPI(
    title="Academic Paper Research Agent API",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "active_sessions": len(SESSIONS),
        "sources": ["arxiv", "semantic_scholar"],
    }


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    session_id, session = get_session(request.session_id)
    return StreamingResponse(
        stream_chat(session_id, session, request.message.strip()),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


frontend_dist = Path(__file__).resolve().parent / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
