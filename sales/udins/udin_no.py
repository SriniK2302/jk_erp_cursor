"""Normalize UDIN numbers for storage and lookup (single canonical form, no duplicates)."""


def normalize_udin(value: str | None) -> str:
    return (value or "").strip().upper()
