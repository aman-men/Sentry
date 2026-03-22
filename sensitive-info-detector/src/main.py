"""Simple entry point for the project."""

from detector import contains_sensitive_info


def main() -> None:
    """Run a small demo of the placeholder detector."""
    sample_text = "Please email jane@example.com for help."
    result = contains_sensitive_info(sample_text)

    print(f"Sample text: {sample_text}")
    print(f"Sensitive info detected: {result}")


if __name__ == "__main__":
    main()
