import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("engagements", "0055_service_engagement_checklists"),
    ]

    operations = [
        migrations.AddField(
            model_name="engagementworkarea",
            name="service_checklist_work_area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="engagement_work_area_instances",
                to="engagements.serviceengagementchecklistworkarea",
            ),
        ),
        migrations.AddField(
            model_name="divisionworkarea",
            name="service_checklist_work_area",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="division_work_area_instances",
                to="engagements.serviceengagementchecklistworkarea",
            ),
        ),
        migrations.AddConstraint(
            model_name="engagementworkarea",
            constraint=models.UniqueConstraint(
                condition=models.Q(service_checklist_work_area__isnull=False),
                fields=("engagement", "service_checklist_work_area"),
                name="uq_engagement_work_area_service_template",
            ),
        ),
        migrations.AddConstraint(
            model_name="divisionworkarea",
            constraint=models.UniqueConstraint(
                condition=models.Q(service_checklist_work_area__isnull=False),
                fields=("division", "service_checklist_work_area"),
                name="uq_division_work_area_service_template",
            ),
        ),
    ]
