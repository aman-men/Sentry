"""Tests for the federated learning simulation."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from detector import train
    from detector.model import load_model
    from federated.client import train_client
    from federated.partition import partition_training_data
    from federated.server import aggregate_client_updates
except ImportError as exc:  # pragma: no cover - dependency-gated in local env
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@unittest.skipIf(IMPORT_ERROR is not None, f"Missing dependencies: {IMPORT_ERROR}")
class FederatedLearningTests(unittest.TestCase):
    """Validate partitioning, client updates, and central aggregation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.detector_dir = tempfile.TemporaryDirectory()
        os.environ["SENSITIVITY_ARTIFACT_DIR"] = cls.detector_dir.name
        train.main()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.detector_dir.cleanup()
        os.environ.pop("SENSITIVITY_ARTIFACT_DIR", None)

    def test_partition_client_training_and_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            federated_root = Path(tmp_dir)
            client_paths = partition_training_data(client_count=3, output_dir=federated_root)

            self.assertEqual(len(client_paths), 3)
            for path in client_paths:
                self.assertTrue(path.exists())

            updates = [
                train_client(path, Path(os.environ["SENSITIVITY_ARTIFACT_DIR"]))
                for path in client_paths
            ]
            self.assertEqual(len(updates), 3)
            self.assertTrue(all(update["sample_count"] > 0 for update in updates))

            global_dir = aggregate_client_updates(
                updates,
                Path(os.environ["SENSITIVITY_ARTIFACT_DIR"]),
                output_dir=federated_root,
            )

            self.assertTrue((global_dir / "vectorizer.pkl").exists())
            self.assertTrue((global_dir / "risk_model.pkl").exists())
            self.assertTrue((global_dir / "label_model.pkl").exists())

            risk_payload = load_model(global_dir / "risk_model.pkl")
            self.assertIn("model", risk_payload)
            self.assertEqual(risk_payload["target"], "risk_level")


if __name__ == "__main__":
    unittest.main()
