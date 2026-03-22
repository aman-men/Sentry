"""FastAPI service for the risk router agent."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

try:
    from .router import route_text
except ImportError:
    from router import route_text

app = FastAPI(title="Risk Router Agent", version="0.1.0")


class RouteRequest(BaseModel):
    text: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route")
def route(request: RouteRequest) -> dict:
    return route_text(request.text)
