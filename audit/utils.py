from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from django.db import models


def serialize_instance(instance: models.Model) -> dict[str, Any]:
    """Serialize a model instance to JSON-compatible dict (business fields only)."""
    data: dict[str, Any] = {}
    for field in instance._meta.fields:
        name = field.name
        if name in ("password",):
            continue
        value = getattr(instance, name)
        data[name] = _serialize_value(field, value)
    return data


def _serialize_value(field: models.Field, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(field, models.ForeignKey):
        if hasattr(value, "pk"):
            return value.pk
        return value
    if isinstance(field, models.OneToOneField):
        return value.pk if hasattr(value, "pk") else value
    if isinstance(field, (models.FileField, models.ImageField)):
        return value.name if value else None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (AttributeError, TypeError):
            return str(value)
    if isinstance(value, (bytes, memoryview)):
        return str(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    return str(value)
