"""Registry for the App Data Update maintenance tool.

A field can be updated through this tool only if it has a cascade function
registered in CASCADE_REGISTRY below. The cascade function is responsible
for updating the field itself plus any dependent data, inside one
transaction, so system integrity is never broken. Fields with no cascade
registered simply do not appear in the field dropdown.
"""

from __future__ import annotations

from typing import Callable

from django.apps import apps
from django.db import transaction

# App labels shown in the table dropdown (business apps only — excludes
# django.contrib.* and audit).
ALLOWED_APP_LABELS = [
    "config",
    "services",
    "udins_source",
    "udins",
    "invoices",
    "engagements",
    "fiscal_years",
    "chart_of_accounts",
    "gl_journal",
    "bank_transactions",
    "teams",
    "grades",
    "qualifications",
]


def list_tables(search: str = "") -> list[dict]:
    """Tables for the dropdown: [{'key': 'app_label.ModelName', 'label': ...}]."""
    search = (search or "").strip().lower()
    rows = []
    for model in apps.get_models():
        app_label = model._meta.app_label
        if app_label not in ALLOWED_APP_LABELS:
            continue
        key = f"{app_label}.{model.__name__}"
        label = f"{app_label} / {model.__name__}"
        if search and search not in label.lower():
            continue
        rows.append({"key": key, "label": label})
    rows.sort(key=lambda r: r["label"])
    return rows


def _get_model(table_key: str):
    app_label, model_name = table_key.split(".", 1)
    return apps.get_model(app_label, model_name)


def list_fields(table_key: str) -> list[dict]:
    """Only fields with a cascade registered for this table are returned."""
    model = _get_model(table_key)
    out = []
    for field_name in CASCADE_REGISTRY.get(table_key, {}):
        field = model._meta.get_field(field_name)
        out.append({"name": field_name, "label": str(field.verbose_name or field_name)})
    out.sort(key=lambda f: f["label"])
    return out


def get_cascade(table_key: str, field_name: str) -> Callable | None:
    return CASCADE_REGISTRY.get(table_key, {}).get(field_name)


def run_update(table_key: str, field_name: str, old_value: str, new_value: str) -> str:
    """Run the registered cascade for one field. Raises ValueError if none registered."""
    cascade = get_cascade(table_key, field_name)
    if cascade is None:
        raise ValueError("No cascade defined for this field. Update blocked.")
    with transaction.atomic():
        return cascade(old_value, new_value)


# ---------------------------------------------------------------------------
# CASCADE_REGISTRY
#
# table_key -> { field_name: cascade_fn }
# cascade_fn(old_value: str, new_value: str) -> str   (summary message)
#
# Add one field at a time, with its cascade fully worked out, before it can
# be updated through this tool.
# ---------------------------------------------------------------------------
CASCADE_REGISTRY: dict[str, dict[str, Callable]] = {
    # e.g. "clients.Client": {"client_code": cascade_client_code},
}
