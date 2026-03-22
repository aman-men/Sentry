"""Training and persistence helpers for the local sensitivity agent."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score

DATASET_FILES = {
    "train": "sensitive_dataset_train.csv",
    "val": "sensitive_dataset_val.csv",
    "test": "sensitive_dataset_test.csv",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _parse_contains(value: Any) -> list[str]:
    if isinstance(value, list):
        return value
    if pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def load_data(data_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    """Load the train/validation/test splits from the existing data directory."""
    root = Path(data_dir) if data_dir else _project_root() / "data"
    datasets: dict[str, pd.DataFrame] = {}

    for split_name, filename in DATASET_FILES.items():
        path = root / filename
        if not path.exists():
            raise FileNotFoundError(f"Required dataset file is missing: {path}")
        frame = pd.read_csv(path)
        expected_columns = {"text", "label", "risk_level", "contains", "department", "action"}
        missing = expected_columns - set(frame.columns)
        if missing:
            raise ValueError(f"Dataset {path} is missing columns: {sorted(missing)}")
        frame = frame.copy()
        frame["text"] = frame["text"].fillna("").astype(str)
        frame["label"] = frame["label"].fillna("").astype(str)
        frame["risk_level"] = frame["risk_level"].fillna("").astype(str)
        frame["contains"] = frame["contains"].apply(_parse_contains)
        datasets[split_name] = frame

    return datasets


def train_model(
    train_df: pd.DataFrame,
    target_column: str,
    random_state: int = 42,
) -> dict[str, Any]:
    """Train a TF-IDF plus logistic regression text classifier."""
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        max_features=20000,
        strip_accents="unicode",
    )
    features = vectorizer.fit_transform(train_df["text"])
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=random_state,
    )
    model.fit(features, train_df[target_column])
    return {"vectorizer": vectorizer, "model": model}


def evaluate_model(
    vectorizer: TfidfVectorizer,
    model: LogisticRegression,
    dataset: pd.DataFrame,
    target_column: str,
) -> dict[str, float]:
    """Evaluate a classifier and return accuracy plus weighted F1."""
    features = vectorizer.transform(dataset["text"])
    predictions = model.predict(features)
    return {
        "accuracy": float(accuracy_score(dataset[target_column], predictions)),
        "f1": float(f1_score(dataset[target_column], predictions, average="weighted")),
    }


def save_model(obj: Any, path: str | Path) -> None:
    """Persist a model artifact with joblib."""
    artifact_path = Path(path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(obj, artifact_path)


def load_model(path: str | Path) -> Any:
    """Load a persisted model artifact."""
    artifact_path = Path(path)
    if not artifact_path.exists():
        raise FileNotFoundError(f"Model artifact not found: {artifact_path}")
    return joblib.load(artifact_path)
