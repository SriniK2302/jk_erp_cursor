"""Service-type helpers for UDIN billing fields."""

from __future__ import annotations


def is_certification_service(service) -> bool:
    if service is None:
        return False
    return "certification" in (getattr(service, "service_desc", None) or "").lower()


def is_audit_service(service) -> bool:
    if service is None:
        return False
    return "audit" in (getattr(service, "service_desc", None) or "").lower()
