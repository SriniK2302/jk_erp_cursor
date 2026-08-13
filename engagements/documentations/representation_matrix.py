"""Per-engagement representation acknowledgment matrix (e.g. MR 02 points)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.http import QueryDict

_MR02_POINTS_PATH = Path(__file__).with_name("mr02_representation_points.json")

# Stored JSON values; labels are for UI only.
REPRESENTATION_POINT_STATUS_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "— Not set"),
    ("applicable", "Applicable"),
    ("not_applicable", "Not applicable"),
    ("complied", "Complied"),
    ("not_complied", "Not complied"),
    ("pending", "Pending / in progress"),
)

_ALLOWED_STATUSES = frozenset(s for s, _ in REPRESENTATION_POINT_STATUS_CHOICES if s)


def is_mr02_documentation(doc) -> bool:
    """True when setup **Fill Word file name suffix** is ``MR 02`` (spacing ignored)."""
    if doc is None:
        return False
    compact = re.sub(
        r"\s+", "", (getattr(doc, "filled_download_label", "") or "").strip()
    ).lower()
    return compact == "mr02"


@lru_cache(maxsize=1)
def load_mr02_point_catalog() -> dict[str, Any]:
    with _MR02_POINTS_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def mr02_point_rows() -> list[dict[str, Any]]:
    data = load_mr02_point_catalog()
    rows = list(data.get("points") or [])
    rows.sort(key=lambda r: (int(r.get("order", 0)), r.get("id", "")))
    return rows


def mr02_catalog_point_ids() -> frozenset[str]:
    return frozenset(str(p.get("id", "")) for p in mr02_point_rows() if p.get("id"))


def parse_representation_matrix_post(post: QueryDict) -> dict[str, dict[str, str]]:
    """Build ``{ point_id: { status, notes } }`` from POST; only known MR02 point ids."""
    allowed_ids = mr02_catalog_point_ids()
    out: dict[str, dict[str, str]] = {}
    for pid in allowed_ids:
        status_key = f"mr02_status_{pid}"
        notes_key = f"mr02_notes_{pid}"
        raw_status = (post.get(status_key) or "").strip()
        if raw_status and raw_status not in _ALLOWED_STATUSES:
            raw_status = ""
        notes = (post.get(notes_key) or "").strip()[:500]
        if raw_status or notes:
            cell: dict[str, str] = {}
            if raw_status:
                cell["status"] = raw_status
            if notes:
                cell["notes"] = notes
            if cell:
                out[pid] = cell
    return out
