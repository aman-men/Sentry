"""FastAPI service for the local response agent."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

try:
    from .agent import chat_local, respond_local
except ImportError:
    from agent import chat_local, respond_local

app = FastAPI(title="Local Response Agent", version="0.1.0")


class RespondLocalRequest(BaseModel):
    text: str
    router_result: dict[str, Any] | None = None


class ChatLocalRequest(BaseModel):
    text: str
    session_messages: list[dict[str, str]]
    router_result: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/respond_local")
def respond(request: RespondLocalRequest) -> dict[str, Any]:
    return respond_local(request.text, router_result=request.router_result)


@app.post("/chat_local")
def chat(request: ChatLocalRequest) -> dict[str, Any]:
    return chat_local(
        request.text,
        session_messages=request.session_messages,
        router_result=request.router_result,
    )
