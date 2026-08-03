from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("keywords", "0002_keywordrun_task_controls")]

    operations = [
        migrations.AlterField(
            model_name="keywordrun",
            name="max_keywords",
            field=models.PositiveSmallIntegerField(default=15),
        ),
    ]
