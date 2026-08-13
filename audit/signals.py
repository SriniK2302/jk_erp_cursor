from __future__ import annotations

from django.db.models.signals import post_save, pre_delete, pre_save

from .context import get_audit_user
from .models import AuditLog
from .registry import get_audited_models
from .utils import serialize_instance

_SNAPSHOT_ATTR = "_audit_snapshot_before"


def _pre_save_capture_old(sender, instance, **kwargs):
    if instance.pk is None:
        setattr(instance, _SNAPSHOT_ATTR, None)
        return
    try:
        old = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        setattr(instance, _SNAPSHOT_ATTR, None)
        return
    setattr(instance, _SNAPSHOT_ATTR, serialize_instance(old))


def _post_save_audit_update(sender, instance, created, **kwargs):
    if created:
        return
    before = getattr(instance, _SNAPSHOT_ATTR, None)
    if hasattr(instance, _SNAPSHOT_ATTR):
        delattr(instance, _SNAPSHOT_ATTR)
    after = serialize_instance(instance)
    actor = get_audit_user()
    AuditLog.objects.create(
        action=AuditLog.Action.UPDATE,
        model_label=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        before_json=before,
        after_json=after,
        actor=actor,
    )


def _pre_delete_audit(sender, instance, **kwargs):
    before = serialize_instance(instance)
    actor = get_audit_user()
    AuditLog.objects.create(
        action=AuditLog.Action.DELETE,
        model_label=instance._meta.label,
        object_id=str(instance.pk),
        object_repr=str(instance)[:255],
        before_json=before,
        after_json=None,
        actor=actor,
    )


def _connect():
    for model in get_audited_models():
        label = model._meta.label
        pre_save.connect(
            _pre_save_capture_old,
            sender=model,
            dispatch_uid=f"audit.pre_save.{label}",
            weak=False,
        )
        post_save.connect(
            _post_save_audit_update,
            sender=model,
            dispatch_uid=f"audit.post_save.{label}",
            weak=False,
        )
        pre_delete.connect(
            _pre_delete_audit,
            sender=model,
            dispatch_uid=f"audit.pre_delete.{label}",
            weak=False,
        )


_connect()
