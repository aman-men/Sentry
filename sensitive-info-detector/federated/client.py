"""Local client-side training for federated detector updates."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

try:
    from detector.model import load_model
except ImportError:
    from model import load_model


def _parse_contains(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    try:
        parsed = ast.literal_eval(str(value))
    except (SyntaxError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def load_client_dataset(path: str | Path) -> pd.DataFrame:
    """Load one client partition."""
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Client dataset not found: {dataset_path}")
    frame = pd.read_csv(dataset_path)
    frame = frame.copy()
    frame["text"] = frame["text"].fillna("").astype(str)
    frame["risk_level"] = frame["risk_level"].fillna("").astype(str)
    frame["contains"] = frame["contains"].apply(_parse_contains)
    return frame


def _load_global_artifacts(global_artifact_dir: str | Path) -> tuple[Any, dict[str, Any]]:
    artifact_dir = Path(global_artifact_dir)
    vectorizer = load_model(artifact_dir / "vectorizer.pkl")
    risk_payload = load_model(artifact_dir / "risk_model.pkl")
    return vectorizer, risk_payload


def train_client(
    client_dataset_path: str | Path,
    global_artifact_dir: str | Path,
    random_state: int = 42,
) -> dict[str, Any]:
    """Train a local risk model using the global vectorizer and return weights only."""
    client_df = load_client_dataset(client_dataset_path)
    vectorizer, risk_payload = _load_global_artifacts(global_artifact_dir)

    features = vectorizer.transform(client_df["text"])
    base_model = risk_payload["model"]
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state,
    )
    model.fit(features, client_df["risk_level"])

    if list(model.classes_) != list(base_model.classes_):
        raise ValueError("Client model classes do not match global detector classes.")

    return {
        "client_id": Path(client_dataset_path).stem,
        "sample_count": int(len(client_df)),
        "classes": model.classes_.tolist(),
        "coef": np.asarray(model.coef_, dtype=float),
        "intercept": np.asarray(model.intercept_, dtype=float),
    }
