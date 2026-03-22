"""Tests for the risk router agent."""

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
    from policy.router import route_from_scan, route_text
    from policy.service import app
except ImportError as exc:  # pragma: no cover - dependency-gated in local env
    TestClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Missing dependencies: {IMPORT_ERROR}")
class RiskRouterTests(unittest.TestCase):
    """Validate policy decisions and detector integration."""

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

    def test_low_risk_scan_routes_to_chatgpt(self) -> None:
        result = route_from_scan(
            {
                "risk_level": "low",
                "label": "safe",
                "confidence": 0.96,
                "categories": [],
                "requires_review": False,
            }
        )
        self.assertEqual(result["route"], "chatgpt")
        self.assertFalse(result["requires_review"])

    def test_high_risk_scan_routes_to_local(self) -> None:
        result = route_from_scan(
            {
                "risk_level": "high",
                "label": "confidential",
                "confidence": 0.88,
                "categories": ["project_codename"],
                "requires_review": False,
            }
        )
        self.assertEqual(result["route"], "local")
        self.assertIn("high risk", result["reason"].lower())

    def test_secret_credentials_route_to_block(self) -> None:
        result = route_from_scan(
            {
                "risk_level": "high",
                "label": "secret_credentials",
                "confidence": 0.99,
                "categories": ["api_key"],
                "requires_review": False,
            }
        )
        self.assertEqual(result["route"], "block")
        self.assertEqual(result["risk_level"], "high")

    def test_low_confidence_requires_review(self) -> None:
        result = route_from_scan(
            {
                "risk_level": "low",
                "label": "internal",
                "confidence": 0.42,
                "categories": [],
                "requires_review": False,
            }
        )
        self.assertTrue(result["requires_review"])

    def test_route_text_works_with_detector_integration(self) -> None:
        result = route_text("Review payroll report for employee E48291 tied to Project Falcon.")
        self.assertEqual(result["route"], "local")
        self.assertEqual(result["risk_level"], "high")

    def test_empty_input_handled_safely(self) -> None:
        result = route_text("")
        self.assertEqual(result["route"], "chatgpt")
        self.assertEqual(result["label"], "safe")

    def test_route_service_endpoint_returns_structured_result(self) -> None:
        response = self.client.post(
            "/route",
            json={"text": "Please review this config with API key sk-live-ALPHA7demo9TOKEN."},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["route"], "block")
        self.assertIn("reason", payload)


if __name__ == "__main__":
    unittest.main()
