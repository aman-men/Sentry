"""End-to-end federated-learning simulation for the sensitivity agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from detector.train import main as train_detector
except ImportError:
    from train import main as train_detector

try:
    from .client import train_client
    from .partition import DEFAULT_CLIENT_COUNT, partition_training_data, partitions_exist
    from .server import aggregate_client_updates
except ImportError:
    from client import train_client
    from partition import DEFAULT_CLIENT_COUNT, partition_training_data, partitions_exist
    from server import aggregate_client_updates


def _default_detector_artifacts() -> Path:
    override = os.environ.get("SENSITIVITY_ARTIFACT_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "detector" / "artifacts"


def main(client_count: int = DEFAULT_CLIENT_COUNT) -> None:
    federated_root = Path(__file__).resolve().parent
    client_dir = federated_root / "client_data"
    global_dir = federated_root / "global_artifacts"
    detector_artifacts = _default_detector_artifacts()

    if not detector_artifacts.exists() or not (detector_artifacts / "risk_model.pkl").exists():
        train_detector()

    if not partitions_exist(client_count=client_count, output_dir=federated_root):
        partition_training_data(client_count=client_count, output_dir=federated_root)

    updates = []
    for index in range(1, client_count + 1):
        client_path = client_dir / f"client_{index}.csv"
        updates.append(train_client(client_path, detector_artifacts))

    aggregate_client_updates(updates, detector_artifacts, output_dir=federated_root)

    total_samples = sum(update["sample_count"] for update in updates)
    print(f"Federated clients: {len(updates)}")
    print(f"Total local samples: {total_samples}")
    print(f"Global detector saved to: {global_dir}")


if __name__ == "__main__":
    main()
