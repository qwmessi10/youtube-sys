from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("smm", "0002_smmpolltask"),
    ]

    operations = [
        migrations.AddField(
            model_name="smmpolltask",
            name="last_error",
            field=models.TextField(blank=True, default="", verbose_name="最近失败原因"),
        ),
    ]
