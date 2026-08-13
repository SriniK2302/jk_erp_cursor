"""Starter utility functions shared across modules."""

from __future__ import annotations


def compact_whitespace(value: str | None) -> str:
    """
    Normalize whitespace in text inputs.

    Example:
        "  hello   world  " -> "hello world"
    """
    if not value:
        return ""
    return " ".join(value.split())


def safe_upper(value: str | None) -> str:
    """Return uppercase text safely for optional values."""
    return compact_whitespace(value).upper()
