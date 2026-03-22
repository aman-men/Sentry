"""Tests for the local response agent."""

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient
    from local_response.agent import chat_local, respond_local
    from local_response.backends import MockLocalBackend, OllamaBackend, OptionalLocalBackendWrapper
    from local_response.service import app
except ImportError as exc:  # pragma: no cover - dependency-gated in local env
    TestClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


LOCAL_ROUTER_RESULT = {
    "route": "local",
    "risk_level": "high",
    "label": "confidential",
    "confidence": 0.91,
    "categories": ["project_codename"],
    "requires_review": False,
    "reason": "Prompt classified as high risk, must remain on device.",
}


@unittest.skipIf(IMPORT_ERROR is not None, f"Missing dependencies: {IMPORT_ERROR}")
class LocalResponseAgentTests(unittest.TestCase):
    """Exercise the local response agent and its service wrapper."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_valid_local_route_returns_structured_response(self) -> None:
        result = respond_local(
            "Summarize the Project Falcon architecture memo for restricted review.",
            router_result=LOCAL_ROUTER_RESULT,
        )
        self.assertEqual(result["handled_by"], "local_response_agent")
        self.assertEqual(result["risk_level"], "high")
        self.assertTrue(result["local_only"])
        self.assertIn("backend_name", result)
        self.assertIn("fallback_used", result)

    def test_non_local_route_raises_error(self) -> None:
        with self.assertRaises(ValueError):
            respond_local(
                "Rewrite this public blog post.",
                router_result={**LOCAL_ROUTER_RESULT, "route": "chatgpt", "risk_level": "low"},
            )

    def test_empty_input_handled_safely(self) -> None:
        result = respond_local("", router_result=LOCAL_ROUTER_RESULT)
        self.assertTrue(result["local_only"])
        self.assertIn("nothing to process", result["response"].lower())

    def test_fallback_to_mock_backend_works(self) -> None:
        os.environ["LOCAL_RESPONSE_BACKEND"] = "unknown_backend"
        backend = OptionalLocalBackendWrapper()
        self.assertIsInstance(backend.backend, MockLocalBackend)
        self.assertEqual(backend.mode_name, "mock_local")
        self.assertEqual(backend.backend_name, "mock")
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)

    def test_mock_backend_can_be_selected_explicitly(self) -> None:
        os.environ["LOCAL_RESPONSE_BACKEND"] = "mock"
        backend = OptionalLocalBackendWrapper()
        self.assertIsInstance(backend.backend, MockLocalBackend)
        self.assertEqual(backend.mode_name, "mock_local")
        self.assertEqual(backend.backend_name, "mock")
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)

    def test_ollama_backend_selected_when_configured(self) -> None:
        os.environ["LOCAL_RESPONSE_BACKEND"] = "ollama"
        backend = OptionalLocalBackendWrapper()
        self.assertIsInstance(backend.backend, OllamaBackend)
        self.assertEqual(backend.mode_name, "backend_local")
        self.assertEqual(backend.backend_name, "ollama")
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)

    def test_ollama_backend_is_default(self) -> None:
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)
        backend = OptionalLocalBackendWrapper()
        self.assertIsInstance(backend.backend, OllamaBackend)
        self.assertEqual(backend.mode_name, "backend_local")
        self.assertEqual(backend.backend_name, "ollama")

    @patch("local_response.backends.httpx.post")
    def test_ollama_backend_falls_back_to_mock_on_error(self, mock_post) -> None:
        mock_post.side_effect = httpx.ConnectError("Ollama unavailable")
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)
        result = respond_local("Handle this locally.", router_result=LOCAL_ROUTER_RESULT)
        self.assertEqual(result["mode"], "backend_local")
        self.assertIn("handled locally", result["response"].lower())
        self.assertEqual(result["backend_name"], "mock")
        self.assertFalse(result["backend_available"])
        self.assertTrue(result["fallback_used"])
        self.assertIn("Ollama unavailable", result["backend_error"])

    @patch("local_response.backends.httpx.post")
    def test_ollama_backend_returns_local_api_response(self, mock_post) -> None:
        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"message": {"content": "Local Ollama reply"}}

        mock_post.return_value = FakeResponse()
        os.environ.pop("LOCAL_RESPONSE_BACKEND", None)
        result = respond_local("Handle this locally.", router_result=LOCAL_ROUTER_RESULT)
        self.assertEqual(result["mode"], "backend_local")
        self.assertEqual(result["response"], "Local Ollama reply")
        self.assertEqual(result["backend_name"], "ollama")
        self.assertTrue(result["backend_available"])
        self.assertFalse(result["fallback_used"])

    def test_output_includes_mode_and_handled_by(self) -> None:
        result = respond_local("Review this restricted note.", router_result=LOCAL_ROUTER_RESULT)
        self.assertEqual(result["handled_by"], "local_response_agent")
        self.assertEqual(result["mode"], "backend_local")
        self.assertIn("backend_available", result)

    def test_chat_local_returns_structured_follow_up(self) -> None:
        result = chat_local(
            "Can you expand on that for leadership?",
            session_messages=[
                {"role": "user", "content": "Review the Project Falcon memo."},
                {"role": "assistant", "content": "This was handled locally."},
            ],
            router_result=LOCAL_ROUTER_RESULT,
        )
        self.assertEqual(result["handled_by"], "local_response_agent")
        self.assertTrue(result["local_only"])
        self.assertIn("backend_name", result)

    def test_chat_service_endpoint_works(self) -> None:
        response = self.client.post(
            "/chat_local",
            json={
                "text": "Please continue the local conversation.",
                "session_messages": [
                    {"role": "user", "content": "Review the Project Falcon memo."},
                    {"role": "assistant", "content": "This was handled locally."},
                ],
                "router_result": LOCAL_ROUTER_RESULT,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["local_only"])
        self.assertIn("response", payload)

    def test_service_endpoint_works(self) -> None:
        response = self.client.post(
            "/respond_local",
            json={
                "text": "Please summarize the confidential Project Orion launch memo.",
                "router_result": LOCAL_ROUTER_RESULT,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["local_only"])
        self.assertEqual(payload["mode"], "backend_local")
        self.assertIn("backend_name", payload)


if __name__ == "__main__":
    unittest.main()
