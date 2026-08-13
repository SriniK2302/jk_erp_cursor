from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0041_divisionworkareadocument_remarks"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DivisionWorkAreaStatusRemark",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("remarks", models.TextField()),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_division_work_area_status_remarks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "work_area",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_remarks",
                        to="engagements.divisionworkarea",
                    ),
                ),
            ],
            options={
                "db_table": "division_work_area_status_remarks",
                "ordering": ["-created_on", "-id"],
            },
        ),
    ]
