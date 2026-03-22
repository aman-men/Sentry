"""Central aggregation for federated sensitivity-detector updates."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import numpy as np

try:
    from detector.model import load_model, save_model
except ImportError:
    from model import load_model, save_model


def global_artifact_dir(base_dir: str | Path | None = None) -> Path:
    if base_dir:
        root = Path(base_dir)
        return root if root.name == "global_artifacts" else root / "global_artifacts"
    return Path(__file__).resolve().parent / "global_artifacts"


def aggregate_client_updates(
    client_updates: list[dict[str, Any]],
    base_artifact_dir: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    """Weighted-average client model parameters and save a new global detector."""
    if not client_updates:
        raise ValueError("No client updates were provided for aggregation.")

    base_dir = Path(base_artifact_dir)
    destination = global_artifact_dir(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    total_samples = sum(update["sample_count"] for update in client_updates)
    if total_samples <= 0:
        raise ValueError("Federated aggregation requires a positive sample count.")

    weighted_coef = sum(update["coef"] * update["sample_count"] for update in client_updates) / total_samples
    weighted_intercept = (
        sum(update["intercept"] * update["sample_count"] for update in client_updates) / total_samples
    )

    vectorizer = load_model(base_dir / "vectorizer.pkl")
    risk_payload = load_model(base_dir / "risk_model.pkl")
    label_payload = load_model(base_dir / "label_model.pkl")

    aggregated_model = risk_payload["model"]
    aggregated_model.coef_ = np.asarray(weighted_coef, dtype=float)
    aggregated_model.intercept_ = np.asarray(weighted_intercept, dtype=float)
    aggregated_model.classes_ = np.asarray(client_updates[0]["classes"])
    aggregated_model.n_features_in_ = aggregated_model.coef_.shape[1]

    save_model(vectorizer, destination / "vectorizer.pkl")
    save_model(
        {
            "vectorizer": vectorizer,
            "model": aggregated_model,
            "target": risk_payload.get("target", "risk_level"),
        },
        destination / "risk_model.pkl",
    )
    save_model(label_payload, destination / "label_model.pkl")

    summary = {
        "client_count": len(client_updates),
        "total_samples": total_samples,
        "classes": client_updates[0]["classes"],
    }
    save_model(summary, destination / "aggregation_summary.pkl")
    shutil.copyfile(base_dir / "vectorizer.pkl", destination / "vectorizer_source_backup.pkl")
    return destination
