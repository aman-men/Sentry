"""Backend abstractions for local-only prompt handling."""

from __future__ import annotations

import os
from typing import Any, Protocol

import httpx


class LocalBackend(Protocol):
    """Minimal interface for local response backends."""

    mode_name: str
    backend_name: str

    def respond(self, text: str, router_result: dict | None = None) -> dict:
        """Return a local-only response for the prompt."""

    def chat(self, messages: list[dict[str, str]], router_result: dict | None = None) -> dict:
        """Return a local-only response for a multi-turn chat history."""


def _latest_user_message(messages: list[dict[str, str]]) -> str:
    """Return the latest user-authored message from a chat transcript."""
    for message in reversed(messages):
        if str(message.get("role", "")).strip().lower() == "user":
            return str(message.get("content", "")).strip()
    return ""


class MockLocalBackend:
    """Reliable placeholder backend used until a real local model is attached."""

    mode_name = "mock_local"
    backend_name = "mock"

    def _empty_response(self) -> dict[str, Any]:
        return {
            "response": (
                "No prompt content was provided. The request stays local, but there is "
                "nothing to process yet."
            ),
            "backend_name": self.backend_name,
            "backend_available": True,
            "fallback_used": False,
            "backend_error": None,
        }

    def respond(self, text: str, router_result: dict | None = None) -> dict:
        if not text.strip():
            return self._empty_response()

        label = (router_result or {}).get("label", "high_risk_prompt")
        return {
            "response": (
                "This prompt was handled locally because it was classified as high risk. "
                f"The current local responder is running in mock mode for label '{label}', "
                "so a stronger on-device model can be attached here later."
            ),
            "backend_name": self.backend_name,
            "backend_available": True,
            "fallback_used": False,
            "backend_error": None,
        }

    def chat(self, messages: list[dict[str, str]], router_result: dict | None = None) -> dict:
        latest_message = _latest_user_message(messages)
        if not latest_message:
            return self._empty_response()

        label = (router_result or {}).get("label", "high_risk_prompt")
        return {
            "response": (
                "This follow-up stayed inside the local workspace because the conversation "
                f"is still classified as '{label}'. In mock mode, the local assistant does "
                f"not run a full model yet, but it received your latest message: \"{latest_message}\"."
            ),
            "backend_name": self.backend_name,
            "backend_available": True,
            "fallback_used": False,
            "backend_error": None,
        }


class OllamaBackend:
    """Local Ollama backend that talks only to the on-device Ollama API."""

    mode_name = "backend_local"
    backend_name = "ollama"

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.model_name = (model_name or os.environ.get("OLLAMA_MODEL", "llama3")).strip() or "llama3"
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.fallback = MockLocalBackend()

    def _fallback_result(
        self,
        latest_text: str,
        messages: list[dict[str, str]] | None,
        router_result: dict | None,
        error_message: str,
    ) -> dict:
        if messages is not None:
            fallback_result = self.fallback.chat(messages, router_result=router_result)
        else:
            fallback_result = self.fallback.respond(latest_text, router_result=router_result)
        fallback_result["fallback_used"] = True
        fallback_result["backend_available"] = False
        fallback_result["backend_error"] = error_message
        return fallback_result

    def _send_chat(self, messages: list[dict[str, str]]) -> dict:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def respond(self, text: str, router_result: dict | None = None) -> dict:
        if not text.strip():
            return {
                "response": self.fallback.respond(text, router_result=router_result)["response"],
                "backend_name": self.backend_name,
                "backend_available": True,
                "fallback_used": False,
                "backend_error": None,
            }

        messages = [{"role": "user", "content": text}]
        try:
            body = self._send_chat(messages)
            message = body.get("message", {})
            content = str(message.get("content", "")).strip()
            if content:
                return {
                    "response": content,
                    "backend_name": self.backend_name,
                    "backend_available": True,
                    "fallback_used": False,
                    "backend_error": None,
                }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return self._fallback_result(text, None, router_result, str(exc))

        return self._fallback_result(
            text,
            None,
            router_result,
            "Ollama returned an empty response.",
        )

    def chat(self, messages: list[dict[str, str]], router_result: dict | None = None) -> dict:
        latest_message = _latest_user_message(messages)
        if not latest_message:
            return {
                "response": self.fallback.chat(messages, router_result=router_result)["response"],
                "backend_name": self.backend_name,
                "backend_available": True,
                "fallback_used": False,
                "backend_error": None,
            }

        try:
            body = self._send_chat(messages)
            message = body.get("message", {})
            content = str(message.get("content", "")).strip()
            if content:
                return {
                    "response": content,
                    "backend_name": self.backend_name,
                    "backend_available": True,
                    "fallback_used": False,
                    "backend_error": None,
                }
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return self._fallback_result(latest_message, messages, router_result, str(exc))

        return self._fallback_result(
            latest_message,
            messages,
            router_result,
            "Ollama returned an empty response.",
        )


class OptionalLocalBackendWrapper:
    """Select a backend by environment configuration and fall back safely."""

    def __init__(self, backend_name: str | None = None) -> None:
        configured_name = (backend_name or os.environ.get("LOCAL_RESPONSE_BACKEND", "ollama")).strip().lower()
        self.configured_backend_name = configured_name or "ollama"
        self.backend = self._resolve_backend()

    def _resolve_backend(self) -> LocalBackend:
        if self.configured_backend_name == "mock":
            return MockLocalBackend()
        if self.configured_backend_name == "ollama":
            return OllamaBackend()
        return MockLocalBackend()

    @property
    def mode_name(self) -> str:
        return self.backend.mode_name

    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "backend_name", "mock")

    def respond(self, text: str, router_result: dict | None = None) -> dict:
        return self.backend.respond(text, router_result=router_result)

    def chat(self, messages: list[dict[str, str]], router_result: dict | None = None) -> dict:
        return self.backend.chat(messages, router_result=router_result)
