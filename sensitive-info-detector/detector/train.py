"""Train the local sensitivity agent from the generated dataset."""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .model import evaluate_model, load_data, save_model, train_model
except ImportError:
    from model import evaluate_model, load_data, save_model, train_model


def _artifact_dir() -> Path:
    override = os.environ.get("SENSITIVITY_ARTIFACT_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "artifacts"


def _build_label_categories(train_df) -> dict[str, list[str]]:
    label_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for _, row in train_df.iterrows():
        for category in row["contains"]:
            label_counts[row["label"]][category] += 1
    return {
        label: [name for name, _ in counter.most_common(6)]
        for label, counter in label_counts.items()
    }


def main() -> None:
    datasets = load_data()
    artifact_dir = _artifact_dir()

    risk_bundle = train_model(datasets["train"], target_column="risk_level")
    label_bundle = train_model(datasets["train"], target_column="label")
    label_categories = _build_label_categories(datasets["train"])

    risk_payload = {
        "vectorizer": risk_bundle["vectorizer"],
        "model": risk_bundle["model"],
        "target": "risk_level",
    }
    label_payload = {
        "model": label_bundle["model"],
        "target": "label",
        "label_to_categories": label_categories,
    }

    save_model(risk_bundle["vectorizer"], artifact_dir / "vectorizer.pkl")
    save_model(risk_payload, artifact_dir / "risk_model.pkl")
    save_model(label_payload, artifact_dir / "label_model.pkl")

    for split_name in ("val", "test"):
        risk_metrics = evaluate_model(
            risk_bundle["vectorizer"],
            risk_bundle["model"],
            datasets[split_name],
            "risk_level",
        )
        label_metrics = evaluate_model(
            risk_bundle["vectorizer"],
            label_bundle["model"],
            datasets[split_name],
            "label",
        )
        print(
            f"{split_name} risk accuracy: {risk_metrics['accuracy']:.4f} | "
            f"risk F1: {risk_metrics['f1']:.4f}"
        )
        print(
            f"{split_name} label accuracy: {label_metrics['accuracy']:.4f} | "
            f"label F1: {label_metrics['f1']:.4f}"
        )

    print(f"Artifacts saved to: {artifact_dir}")


if __name__ == "__main__":
    main()
