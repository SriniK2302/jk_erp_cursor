from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0039_timesession_task_description"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DivisionWorkAreaConfirmationMailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mail_type", models.CharField(default="confirmation", max_length=30)),
                ("recipient_email", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=255)),
                ("sent_on", models.DateTimeField(auto_now_add=True)),
                (
                    "assignment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="confirmation_mail_logs",
                        to="engagements.divisionworkareateamassignment",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sent_division_work_area_confirmation_mails",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "division_work_area_confirmation_mail_logs",
                "ordering": ["-sent_on", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="divisionworkareaconfirmationmaillog",
            constraint=models.UniqueConstraint(
                fields=("assignment", "mail_type"),
                name="uq_division_work_area_confirmation_mail_once",
            ),
        ),
    ]
