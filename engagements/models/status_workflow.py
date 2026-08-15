from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .constants import (
    CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_SCHEDULED,
)
from .division_work_area import DivisionWorkArea
from .division_work_area_document import DivisionWorkAreaDocument
from .division_work_area_period import DivisionWorkAreaPeriod
from .engagement import Engagement
from .engagement_division import EngagementDivision
from .engagement_division_documentation_map_attachment import (
    EngagementDivisionDocumentationMapAttachment,
)
from .engagement_documentation_map_attachment import EngagementDocumentationMapAttachment
from .engagement_schedule import EngagementSchedule
from .engagement_work_area import EngagementWorkArea
from .engagement_work_area_document import EngagementWorkAreaDocument
from .engagement_work_area_period import EngagementWorkAreaPeriod

def _close_children_for_engagement(engagement_id, closed_on):
    if closed_on is None:
        return
    EngagementDivision.objects.filter(
        engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementWorkAreaPeriod.objects.filter(
        work_area__engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    DivisionWorkAreaPeriod.objects.filter(
        work_area__division__engagement_id=engagement_id,
        actual_finish__isnull=True,
    ).update(
        actual_finish=closed_on,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementDivision.objects.filter(engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    EngagementWorkArea.objects.filter(engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )
    DivisionWorkArea.objects.filter(division__engagement_id=engagement_id).update(
        status=STATUS_COMPLETED,
        closure_source=CLOSURE_SOURCE_ENGAGEMENT_AUTO,
    )


def _apply_actual_start_for_engagement(engagement_id, started_on):
    if started_on is None:
        return
    EngagementDivision.objects.filter(
        engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)
    EngagementWorkAreaPeriod.objects.filter(
        work_area__engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)
    DivisionWorkAreaPeriod.objects.filter(
        work_area__division__engagement_id=engagement_id,
        actual_start__isnull=True,
    ).update(actual_start=started_on)


def _set_engagement_status(engagement_id):
    engagement = Engagement.objects.filter(pk=engagement_id).first()
    if engagement is None:
        return
    has_actual_finish = engagement.schedules.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    else:
        has_docs = (
            EngagementDocumentationMapAttachment.objects.filter(
                documentation_map__engagement_id=engagement_id
            ).exists()
            or EngagementDivisionDocumentationMapAttachment.objects.filter(
                documentation_map__division__engagement_id=engagement_id
            ).exists()
            or EngagementWorkAreaDocument.objects.filter(
                work_area__engagement_id=engagement_id
            ).exists()
            or DivisionWorkAreaDocument.objects.filter(
                work_area__division__engagement_id=engagement_id
            ).exists()
        )
        if has_docs:
            next_status = STATUS_IN_PROGRESS
        elif engagement.schedules.filter(planned_finish__isnull=False).exists():
            next_status = STATUS_SCHEDULED
        else:
            next_status = STATUS_PENDING
    Engagement.objects.filter(pk=engagement_id).update(status=next_status)


def _set_division_status(division_id):
    division = EngagementDivision.objects.filter(pk=division_id).first()
    if division is None:
        return
    if division.actual_finish is not None:
        next_status = STATUS_COMPLETED
    else:
        has_docs = (
            EngagementDivisionDocumentationMapAttachment.objects.filter(
                documentation_map__division_id=division_id
            ).exists()
            or DivisionWorkAreaDocument.objects.filter(work_area__division_id=division_id).exists()
        )
        if has_docs:
            next_status = STATUS_IN_PROGRESS
        elif division.planned_finish is not None:
            next_status = STATUS_SCHEDULED
        else:
            next_status = STATUS_PENDING
    EngagementDivision.objects.filter(pk=division_id).update(status=next_status)


def _set_engagement_work_area_status(work_area_id):
    work_area = EngagementWorkArea.objects.filter(pk=work_area_id).first()
    if work_area is None:
        return
    has_actual_finish = work_area.schedule_rows.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    elif work_area.documents.exists():
        next_status = STATUS_IN_PROGRESS
    elif work_area.schedule_rows.filter(planned_finish__isnull=False).exists():
        next_status = STATUS_SCHEDULED
    else:
        next_status = STATUS_PENDING
    EngagementWorkArea.objects.filter(pk=work_area_id).update(status=next_status)


def _set_division_work_area_status(work_area_id):
    work_area = DivisionWorkArea.objects.filter(pk=work_area_id).first()
    if work_area is None:
        return
    has_actual_finish = work_area.schedule_rows.filter(actual_finish__isnull=False).exists()
    if has_actual_finish:
        next_status = STATUS_COMPLETED
    elif work_area.documents.exists():
        next_status = STATUS_IN_PROGRESS
    elif work_area.schedule_rows.filter(planned_finish__isnull=False).exists():
        next_status = STATUS_SCHEDULED
    else:
        next_status = STATUS_PENDING
    DivisionWorkArea.objects.filter(pk=work_area_id).update(status=next_status)


@receiver(post_save, sender=Engagement)
def _engagement_status_on_save(sender, instance, **kwargs):
    _set_engagement_status(instance.pk)


@receiver(post_save, sender=EngagementSchedule)
@receiver(post_delete, sender=EngagementSchedule)
def _engagement_status_on_schedule_change(sender, instance, **kwargs):
    completed_on = (
        EngagementSchedule.objects.filter(
            engagement_id=instance.engagement_id,
            actual_finish__isnull=False,
        )
        .order_by("-actual_finish")
        .values_list("actual_finish", flat=True)
        .first()
    )
    started_on = None
    if completed_on is not None:
        started_on = (
            EngagementSchedule.objects.filter(
                engagement_id=instance.engagement_id,
                actual_start__isnull=False,
            )
            .order_by("actual_start")
            .values_list("actual_start", flat=True)
            .first()
        )
    _apply_actual_start_for_engagement(instance.engagement_id, started_on)
    _close_children_for_engagement(instance.engagement_id, completed_on)
    _set_engagement_status(instance.engagement_id)


@receiver(post_save, sender=EngagementDocumentationMapAttachment)
@receiver(post_delete, sender=EngagementDocumentationMapAttachment)
def _engagement_status_on_engagement_doc_change(sender, instance, **kwargs):
    _set_engagement_status(instance.documentation_map.engagement_id)


@receiver(post_save, sender=EngagementDivisionDocumentationMapAttachment)
@receiver(post_delete, sender=EngagementDivisionDocumentationMapAttachment)
def _status_on_division_doc_change(sender, instance, **kwargs):
    division_id = instance.documentation_map.division_id
    _set_division_status(division_id)
    _set_engagement_status(instance.documentation_map.division.engagement_id)


@receiver(post_save, sender=EngagementWorkAreaDocument)
@receiver(post_delete, sender=EngagementWorkAreaDocument)
def _status_on_engagement_work_area_doc_change(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.work_area_id)
    _set_engagement_status(instance.work_area.engagement_id)


@receiver(post_save, sender=DivisionWorkAreaDocument)
@receiver(post_delete, sender=DivisionWorkAreaDocument)
def _status_on_division_work_area_doc_change(sender, instance, **kwargs):
    _set_division_work_area_status(instance.work_area_id)
    _set_division_status(instance.work_area.division_id)
    _set_engagement_status(instance.work_area.division.engagement_id)


@receiver(post_save, sender=EngagementDivision)
def _division_status_on_save(sender, instance, **kwargs):
    _set_division_status(instance.pk)


@receiver(post_save, sender=EngagementWorkArea)
def _engagement_work_area_status_on_save(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.pk)


@receiver(post_save, sender=DivisionWorkArea)
def _division_work_area_status_on_save(sender, instance, **kwargs):
    _set_division_work_area_status(instance.pk)


@receiver(post_save, sender=EngagementWorkAreaPeriod)
@receiver(post_delete, sender=EngagementWorkAreaPeriod)
def _engagement_work_area_status_on_period_change(sender, instance, **kwargs):
    _set_engagement_work_area_status(instance.work_area_id)


@receiver(post_save, sender=DivisionWorkAreaPeriod)
@receiver(post_delete, sender=DivisionWorkAreaPeriod)
def _division_work_area_status_on_period_change(sender, instance, **kwargs):
    _set_division_work_area_status(instance.work_area_id)
