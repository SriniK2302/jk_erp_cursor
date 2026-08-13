"""Starter utility functions shared across modules."""

from __future__ import annotations
from hashlib import sha256
from pathlib import Path


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

_HASH_CHUNK_SIZE = 1024 * 1024


def file_sha256(path: Path) -> str:
    """Return the SHA-256 hex signature of a file's contents."""
    hasher = sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(_HASH_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
