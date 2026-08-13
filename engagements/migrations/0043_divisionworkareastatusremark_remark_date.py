from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("engagements", "0042_divisionworkareastatusremark"),
    ]

    operations = [
        migrations.AddField(
            model_name="divisionworkareastatusremark",
            name="remark_date",
            field=models.DateField(default=timezone.localdate),
            preserve_default=False,
        ),
    ]
