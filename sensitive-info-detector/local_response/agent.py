"""Public API for the local response agent."""

from __future__ import annotations

from typing import Any

try:
    from .backends import OptionalLocalBackendWrapper
except ImportError:
    from backends import OptionalLocalBackendWrapper


def validate_local_request(text: str, router_result: dict | None = None) -> None:
    """Validate that the request is safe to handle with the local responder."""
    if router_result is not None and router_result.get("route") != "local":
        raise ValueError(
            "Local Response Agent only accepts requests routed to 'local'. "
            f"Received route={router_result.get('route')!r}."
        )
    if text is None:
        raise ValueError("Local Response Agent requires text input.")


def _response_payload(context: dict[str, Any], backend_result: dict[str, Any], mode_name: str) -> dict[str, Any]:
    """Build the common structured response for one-shot and chat paths."""
    return {
        "handled_by": "local_response_agent",
        "mode": mode_name,
        "response": backend_result["response"],
        "risk_level": str(context.get("risk_level", "high")),
        "label": str(context.get("label", "unknown")),
        "categories": list(context.get("categories", [])),
        "requires_review": bool(context.get("requires_review", False)),
        "backend_name": backend_result["backend_name"],
        "backend_available": bool(backend_result["backend_available"]),
        "fallback_used": bool(backend_result["fallback_used"]),
        "backend_error": backend_result.get("backend_error"),
        "local_only": True,
    }


def respond_local(text: str, router_result: dict | None = None) -> dict[str, Any]:
    """Handle a high-risk prompt locally and return structured metadata."""
    validate_local_request(text, router_result=router_result)

    cleaned_text = str(text).strip()
    backend = OptionalLocalBackendWrapper()
    context = router_result or {}
    backend_result = backend.respond(cleaned_text, router_result=context)
    return _response_payload(context, backend_result, backend.mode_name)


def chat_local(
    text: str,
    session_messages: list[dict[str, str]],
    router_result: dict | None = None,
) -> dict[str, Any]:
    """Continue a local-only conversation using the prior local chat history."""
    validate_local_request(text, router_result=router_result)

    cleaned_text = str(text).strip()
    history = [
        {
            "role": str(message.get("role", "")).strip().lower(),
            "content": str(message.get("content", "")),
        }
        for message in session_messages
        if isinstance(message, dict)
    ]
    history.append({"role": "user", "content": cleaned_text})

    backend = OptionalLocalBackendWrapper()
    context = router_result or {}
    backend_result = backend.chat(history, router_result=context)
    return _response_payload(context, backend_result, backend.mode_name)
