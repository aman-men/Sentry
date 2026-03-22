"""FastAPI service for the local sensitivity agent."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

try:
    from .infer import scan_text
except ImportError:
    from infer import scan_text

app = FastAPI(title="Local Sensitivity Agent", version="0.1.0")


class ScanRequest(BaseModel):
    text: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scan")
def scan(request: ScanRequest) -> dict:
    return scan_text(request.text)
