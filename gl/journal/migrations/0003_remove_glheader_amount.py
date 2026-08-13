from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("gl_journal", "0002_signed_amount_columns"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="glheader",
            name="amount",
        ),
    ]
