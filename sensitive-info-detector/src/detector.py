"""Placeholder logic for sensitive information detection."""

import re


def contains_sensitive_info(text: str) -> bool:
    """Return True when the text looks like it contains an email address."""
    email_pattern = r"\b[\w.-]+@[\w.-]+\.\w+\b"
    return bool(re.search(email_pattern, text))
