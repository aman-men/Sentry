"""Tests for the one-command gateway service."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from fastapi.testclient import TestClient
    from detector import infer, train
    from gateway.service import LOCAL_CHAT_SESSIONS, app, continue_local_chat, process_prompt
except ImportError as exc:  # pragma: no cover - dependency-gated in local env
    TestClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Missing dependencies: {IMPORT_ERROR}")
class GatewayServiceTests(unittest.TestCase):
    """Exercise the extension-facing gateway contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["SENSITIVITY_ARTIFACT_DIR"] = cls.temp_dir.name
        train.main()
        infer._CACHE = None
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()
        os.environ.pop("SENSITIVITY_ARTIFACT_DIR", None)
        infer._CACHE = None

    def setUp(self) -> None:
        LOCAL_CHAT_SESSIONS.clear()

    def test_low_risk_prompt_returns_chatgpt_route(self) -> None:
        result = process_prompt("Rewrite this public blog post about Python testing.", "chatgpt")
        self.assertEqual(result["route"], "chatgpt")
        self.assertNotIn("local_response", result)

    def test_high_risk_prompt_returns_local_with_local_response(self) -> None:
        result = process_prompt(
            "Review payroll report for employee E48291 tied to Project Falcon.",
            "chatgpt",
        )
        self.assertEqual(result["route"], "local")
        self.assertIn("local_response", result)
        self.assertIn("local_session_id", result)
        self.assertIn("local_mode", result)
        self.assertIn("local_backend", result)
        self.assertIn("local_backend_available", result)
        self.assertIn("local_fallback_used", result)

    def test_secret_prompt_returns_block(self) -> None:
        result = process_prompt(
            "Please review this config with API key sk-live-ALPHA7demo9TOKEN.",
            "gemini",
        )
        self.assertEqual(result["route"], "block")
        self.assertNotIn("local_response", result)

    def test_empty_prompt_is_handled_consistently(self) -> None:
        result = process_prompt("", "chatgpt")
        self.assertEqual(result["route"], "chatgpt")
        self.assertEqual(result["risk_level"], "low")

    def test_gateway_endpoint_matches_extension_contract(self) -> None:
        response = self.client.post(
            "/process_prompt",
            json={"text": "Summarize these internal sprint notes for next week.", "platform": "chatgpt"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("route", payload)
        self.assertIn("risk_level", payload)
        self.assertIn("label", payload)
        self.assertIn("confidence", payload)
        self.assertIn("categories", payload)
        self.assertIn("requires_review", payload)
        self.assertIn("reason", payload)

    def test_gateway_local_response_includes_extension_metadata(self) -> None:
        response = self.client.post(
            "/process_prompt",
            json={
                "text": "Review payroll report for employee E48291 tied to Project Falcon.",
                "platform": "chatgpt",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "local")
        self.assertIn("local_response", payload)
        self.assertIn("local_session_id", payload)
        self.assertIn("local_mode", payload)
        self.assertIn("local_backend", payload)
        self.assertIn("local_backend_available", payload)
        self.assertIn("local_fallback_used", payload)

    def test_continue_local_chat_returns_follow_up_response(self) -> None:
        initial = process_prompt(
            "Review payroll report for employee E48291 tied to Project Falcon.",
            "chatgpt",
        )
        result = continue_local_chat(
            session_id=initial["local_session_id"],
            text="Can you make that easier for finance leadership to read?",
            platform="chatgpt",
        )
        self.assertEqual(result["session_id"], initial["local_session_id"])
        self.assertIn("response", result)
        self.assertIn("backend_name", result)

    def test_chat_local_endpoint_returns_404_for_unknown_session(self) -> None:
        response = self.client.post(
            "/chat_local",
            json={
                "session_id": "missing-session",
                "text": "Continue locally.",
                "platform": "chatgpt",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_malformed_request_returns_422(self) -> None:
        response = self.client.post("/process_prompt", json={"platform": "chatgpt"})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
