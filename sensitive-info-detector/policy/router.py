"""Risk router logic built on top of the local sensitivity agent."""

from __future__ import annotations

from typing import Any

try:
    from detector.infer import scan_text
except ImportError:
    from infer import scan_text

CONFIDENCE_REVIEW_THRESHOLD = 0.60


def route_from_scan(
    scan_result: dict[str, Any], review_threshold: float = CONFIDENCE_REVIEW_THRESHOLD
) -> dict[str, Any]:
    """Convert a sensitivity scan result into a routing decision."""
    risk_level = str(scan_result.get("risk_level", "low"))
    label = str(scan_result.get("label", "safe"))
    confidence = float(scan_result.get("confidence", 0.0))
    categories = list(scan_result.get("categories", []))
    requires_review = bool(scan_result.get("requires_review", False)) or confidence < review_threshold

    if label == "secret_credentials":
        route = "block"
        reason = "Prompt contains credential-like content and is blocked."
        risk_level = "high"
    elif risk_level == "high":
        route = "local"
        reason = "Prompt classified as high risk, must remain on device."
    else:
        route = "chatgpt"
        reason = "Prompt classified as low risk, safe for ChatGPT."

    return {
        "route": route,
        "risk_level": risk_level,
        "label": label,
        "confidence": round(confidence, 4),
        "categories": categories,
        "requires_review": requires_review,
        "reason": reason,
    }


def route_text(text: str, review_threshold: float = CONFIDENCE_REVIEW_THRESHOLD) -> dict[str, Any]:
    """Run the sensitivity agent locally and return the final routing decision."""
    if text is None or not str(text).strip():
        return {
            "route": "chatgpt",
            "risk_level": "low",
            "label": "safe",
            "confidence": 0.0,
            "categories": [],
            "requires_review": False,
            "reason": "Empty prompt treated as low risk and safe for ChatGPT.",
        }

    scan_result = scan_text(str(text).strip())
    return route_from_scan(scan_result, review_threshold=review_threshold)
