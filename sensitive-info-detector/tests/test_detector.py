"""Tests for the local sensitivity agent."""

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
    from detector.model import load_model
    from detector.service import app
except ImportError as exc:  # pragma: no cover - dependency-gated in local env
    TestClient = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Missing dependencies: {IMPORT_ERROR}")
class SensitivityAgentTests(unittest.TestCase):
    """Exercise training, artifact loading, and service inference."""

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

    def test_model_loads(self) -> None:
        artifact_dir = Path(os.environ["SENSITIVITY_ARTIFACT_DIR"])
        vectorizer = load_model(artifact_dir / "vectorizer.pkl")
        risk_payload = load_model(artifact_dir / "risk_model.pkl")
        label_payload = load_model(artifact_dir / "label_model.pkl")

        self.assertIsNotNone(vectorizer)
        self.assertIn("model", risk_payload)
        self.assertIn("model", label_payload)

    def test_scan_works(self) -> None:
        result = infer.scan_text("Please summarize these internal sprint notes for next week.")
        self.assertIn(result["risk_level"], {"low", "high"})
        self.assertIsInstance(result["categories"], list)

    def test_empty_input_works(self) -> None:
        result = infer.scan_text("")
        self.assertEqual(result["risk_level"], "low")
        self.assertEqual(result["label"], "safe")
        self.assertEqual(result["confidence"], 0.0)

    def test_secret_example_is_high_risk(self) -> None:
        result = infer.scan_text("Please review this config with API key sk-live-ALPHA7demo9TOKEN.")
        self.assertEqual(result["risk_level"], "high")
        self.assertIn("api_key", result["categories"])

    def test_service_scan_endpoint_returns_result(self) -> None:
        response = self.client.post("/scan", json={"text": "Review payroll report for employee E48291."})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["risk_level"], "high")
        self.assertIn("categories", payload)


if __name__ == "__main__":
    unittest.main()
