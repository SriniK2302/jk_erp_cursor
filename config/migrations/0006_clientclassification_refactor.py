# Generated manually on 2026-04-15

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def forward_populate_client_classification(apps, schema_editor):
    user_app, user_model = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app, user_model)
    Client = apps.get_model("config", "Client")
    ClientClassification = apps.get_model("config", "ClientClassification")

    actor = User.objects.order_by("id").first()
    if actor is None:
        actor = User.objects.create(username="system_migration")

    value_to_name = {
        "aop": "AOP",
        "huf": "HUF",
        "individual": "Individual",
        "llp": "LLP",
        "listed_company": "Listed Company",
        "others": "Others",
        "partnership_firm": "Partnership Firm",
        "private_bank": "Private Bank",
        "private_limited_company": "Private Limited Company",
        "public_limited_company": "Public Limited Company",
        "public_sector_bank": "Public Sector Bank",
        "sole_propreitprship": "Sole-propreitprship",
        "trust": "Trust",
    }

    names_in_order = [
        "AOP",
        "HUF",
        "Individual",
        "LLP",
        "Listed Company",
        "Others",
        "Partnership Firm",
        "Private Bank",
        "Private Limited Company",
        "Public Limited Company",
        "Public Sector Bank",
        "Sole-propreitprship",
        "Trust",
    ]

    name_to_obj = {}
    for name in names_in_order:
        obj, _ = ClientClassification.objects.get_or_create(
            classification_name=name,
            defaults={"created_by_id": actor.pk},
        )
        name_to_obj[name] = obj

    default_obj = name_to_obj["Others"]
    for client in Client.objects.all():
        classification_value = getattr(client, "classification", None)
        mapped_name = value_to_name.get(classification_value, "Others")
        client.classification_ref_id = name_to_obj.get(mapped_name, default_obj).pk
        client.save(update_fields=["classification_ref"])


class Migration(migrations.Migration):

    dependencies = [
        ("config", "0005_alter_client_classification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientClassification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("classification_name", models.CharField(max_length=120, unique=True)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                ("updated_on", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_client_classifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "client_classifications",
                "ordering": ["classification_name"],
            },
        ),
        migrations.AddField(
            model_name="client",
            name="classification_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="clients",
                to="config.clientclassification",
            ),
        ),
        migrations.RunPython(forward_populate_client_classification, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="client",
            name="classification",
        ),
        migrations.RenameField(
            model_name="client",
            old_name="classification_ref",
            new_name="classification",
        ),
        migrations.AlterField(
            model_name="client",
            name="classification",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="clients",
                to="config.clientclassification",
            ),
        ),
    ]
