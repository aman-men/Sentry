"""Single-entry FastAPI gateway for the local prompt-security pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from detector.infer import scan_text
from local_response.agent import chat_local, respond_local
from policy.router import route_from_scan

app = FastAPI(title="AI Security Pipeline Gateway", version="0.1.0")

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "detector" / "artifacts"
REQUIRED_ARTIFACTS = ("vectorizer.pkl", "risk_model.pkl", "label_model.pkl")
LOCAL_CHAT_SESSIONS: dict[str, dict[str, Any]] = {}


class ProcessPromptRequest(BaseModel):
    text: str
    platform: Literal["chatgpt", "gemini"]


class ChatLocalRequest(BaseModel):
    session_id: str
    text: str
    platform: Literal["chatgpt", "gemini"] | None = None


def ensure_detector_artifacts() -> None:
    """Fail clearly if the detector has not been trained yet."""
    missing = [name for name in REQUIRED_ARTIFACTS if not (ARTIFACT_DIR / name).exists()]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            "Detector artifacts are missing. Run '.\\.venv\\Scripts\\python.exe detector\\train.py' "
            f"before starting the gateway. Missing: {missing_list}"
        )


def process_prompt(text: str, platform: str) -> dict:
    """Run detector -> router -> local responder as one in-process flow."""
    ensure_detector_artifacts()

    scan_result = scan_text(text)
    router_result = route_from_scan(scan_result)

    payload = {
        "route": router_result["route"],
        "risk_level": router_result["risk_level"],
        "label": router_result["label"],
        "confidence": router_result["confidence"],
        "categories": router_result["categories"],
        "requires_review": router_result["requires_review"],
        "reason": router_result["reason"],
    }

    if router_result["route"] == "local":
        local_result = respond_local(text, router_result=router_result)
        session_id = create_local_session(
            text=text,
            platform=platform,
            router_result=router_result,
            local_result=local_result,
        )
        payload["local_response"] = local_result["response"]
        payload["local_session_id"] = session_id
        payload["local_mode"] = local_result["mode"]
        payload["local_backend"] = local_result["backend_name"]
        payload["local_backend_available"] = local_result["backend_available"]
        payload["local_fallback_used"] = local_result["fallback_used"]
        payload["local_backend_error"] = local_result.get("backend_error")

    return payload


def create_local_session(
    text: str,
    platform: str,
    router_result: dict[str, Any],
    local_result: dict[str, Any],
) -> str:
    """Create a new in-memory local chat session seeded from the intercepted prompt."""
    session_id = str(uuid4())
    LOCAL_CHAT_SESSIONS[session_id] = {
        "platform": platform,
        "router_result": dict(router_result),
        "messages": [
            {"role": "user", "content": text},
            {"role": "assistant", "content": local_result["response"]},
        ],
    }
    return session_id


def continue_local_chat(session_id: str, text: str, platform: str | None = None) -> dict[str, Any]:
    """Continue an existing local-only chat session."""
    ensure_detector_artifacts()

    session = LOCAL_CHAT_SESSIONS.get(session_id)
    if session is None:
        raise KeyError(session_id)

    if platform and session.get("platform") != platform:
        session["platform"] = platform

    chat_result = chat_local(
        text=text,
        session_messages=list(session["messages"]),
        router_result=session["router_result"],
    )
    session["messages"].append({"role": "user", "content": text})
    session["messages"].append({"role": "assistant", "content": chat_result["response"]})
    return {
        "session_id": session_id,
        "response": chat_result["response"],
        "backend_name": chat_result["backend_name"],
        "backend_available": chat_result["backend_available"],
        "fallback_used": chat_result["fallback_used"],
        "backend_error": chat_result.get("backend_error"),
        "requires_review": chat_result["requires_review"],
    }


@app.get("/health")
def health() -> dict[str, object]:
    try:
        ensure_detector_artifacts()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "artifacts_ready": True, "local_sessions": len(LOCAL_CHAT_SESSIONS)}


@app.post("/process_prompt")
def process(request: ProcessPromptRequest) -> dict:
    try:
        return process_prompt(request.text, request.platform)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/chat_local")
def chat_local_endpoint(request: ChatLocalRequest) -> dict[str, Any]:
    try:
        return continue_local_chat(request.session_id, request.text, request.platform)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Local chat session expired or was not found. Start a new local prompt.",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
