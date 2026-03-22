"""Inference entrypoint for the local sensitivity agent."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

try:
    from .model import load_model
except ImportError:
    from model import load_model

ARTIFACT_FILENAMES = {
    "vectorizer": "vectorizer.pkl",
    "risk_model": "risk_model.pkl",
    "label_model": "label_model.pkl",
}

REGEX_CATEGORY_PATTERNS = {
    "api_key": re.compile(r"\bsk-live-[A-Za-z0-9._-]+\b", re.IGNORECASE),
    "token": re.compile(r"\bghp_[A-Za-z0-9_]+\b|\bsession_secret\s*=\s*[\w!@#$%^&*.-]+\b", re.IGNORECASE),
    "cloud_credential": re.compile(r"\bAKIA[A-Z0-9]{8,}\b", re.IGNORECASE),
    "password_or_secret": re.compile(r"\b(?:password|secret)\s*[:=]\s*[\w!@#$%^&*.-]+\b", re.IGNORECASE),
    "employee_id": re.compile(r"\bE\d{5}\b"),
    "customer_account_id": re.compile(r"\bA\d{6}\b"),
    "case_id": re.compile(r"\bCASE-\d{4}\b", re.IGNORECASE),
    "invoice_id": re.compile(r"\bINV-\d{5}\b", re.IGNORECASE),
    "project_codename": re.compile(r"\bProject\s+(Falcon|Orion|Atlas|Lantern|Redwood)\b", re.IGNORECASE),
}

HIGH_RISK_CATEGORY_SET = {
    "api_key",
    "token",
    "cloud_credential",
    "password_or_secret",
    "employee_id",
    "customer_account_id",
    "case_id",
    "invoice_id",
    "project_codename",
}

_CACHE: dict[str, Any] | None = None


def _artifact_dir() -> Path:
    override = os.environ.get("SENSITIVITY_ARTIFACT_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "artifacts"


def _load_artifacts() -> dict[str, Any]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    artifact_dir = _artifact_dir()
    vectorizer = load_model(artifact_dir / ARTIFACT_FILENAMES["vectorizer"])
    risk_payload = load_model(artifact_dir / ARTIFACT_FILENAMES["risk_model"])
    label_payload = load_model(artifact_dir / ARTIFACT_FILENAMES["label_model"])
    _CACHE = {
        "vectorizer": vectorizer,
        "risk_model": risk_payload["model"],
        "label_model": label_payload["model"],
        "label_to_categories": label_payload.get("label_to_categories", {}),
    }
    return _CACHE


def _regex_categories(text: str) -> list[str]:
    categories = [
        category
        for category, pattern in REGEX_CATEGORY_PATTERNS.items()
        if pattern.search(text)
    ]
    return sorted(set(categories))


def _predict(text: str) -> dict[str, Any]:
    artifacts = _load_artifacts()
    features = artifacts["vectorizer"].transform([text])

    risk_model = artifacts["risk_model"]
    label_model = artifacts["label_model"]

    risk_prediction = str(risk_model.predict(features)[0])
    label_prediction = str(label_model.predict(features)[0])

    risk_probabilities = risk_model.predict_proba(features)[0]
    risk_classes = list(risk_model.classes_)
    confidence = float(max(risk_probabilities))
    probability_by_class = {
        str(name): float(probability)
        for name, probability in zip(risk_classes, risk_probabilities)
    }

    categories = set(artifacts["label_to_categories"].get(label_prediction, []))
    regex_categories = _regex_categories(text)
    categories.update(regex_categories)

    if any(category in HIGH_RISK_CATEGORY_SET for category in regex_categories):
        risk_prediction = "high"
        confidence = max(confidence, 0.95)
        if label_prediction == "safe":
            label_prediction = "secret_credentials" if any(
                category in {"api_key", "token", "cloud_credential", "password_or_secret"}
                for category in regex_categories
            ) else "confidential"
    elif probability_by_class.get("high", 0.0) > probability_by_class.get("low", 0.0):
        risk_prediction = "high"

    requires_review = confidence < 0.60 or (
        risk_prediction == "low" and bool(regex_categories)
    )

    return {
        "risk_level": risk_prediction,
        "label": label_prediction,
        "confidence": round(confidence, 4),
        "categories": sorted(categories),
        "requires_review": requires_review,
    }


def scan_text(text: str) -> dict:
    """Scan a prompt and return structured sensitivity metadata."""
    if text is None or not str(text).strip():
        return {
            "risk_level": "low",
            "label": "safe",
            "confidence": 0.0,
            "categories": [],
            "requires_review": False,
        }
    return _predict(str(text).strip())
