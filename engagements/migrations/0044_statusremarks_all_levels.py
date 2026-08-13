from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0043_divisionworkareastatusremark_remark_date"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EngagementStatusRemark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("remark_date", models.DateField()),
                ("remarks", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_engagement_status_remarks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "engagement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_remarks",
                        to="engagements.engagement",
                    ),
                ),
            ],
            options={
                "db_table": "engagement_status_remarks",
                "ordering": ["-remark_date", "-created_on", "-id"],
            },
        ),
        migrations.CreateModel(
            name="EngagementDivisionStatusRemark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("remark_date", models.DateField()),
                ("remarks", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_engagement_division_status_remarks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "division",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_remarks",
                        to="engagements.engagementdivision",
                    ),
                ),
            ],
            options={
                "db_table": "engagement_division_status_remarks",
                "ordering": ["-remark_date", "-created_on", "-id"],
            },
        ),
        migrations.CreateModel(
            name="EngagementWorkAreaStatusRemark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("remark_date", models.DateField()),
                ("remarks", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_engagement_work_area_status_remarks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_area",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_remarks",
                        to="engagements.engagementworkarea",
                    ),
                ),
            ],
            options={
                "db_table": "engagement_work_area_status_remarks",
                "ordering": ["-remark_date", "-created_on", "-id"],
            },
        ),
    ]
