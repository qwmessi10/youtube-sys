from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("keywords", "0005_scoring_model_2")]

    operations = [
        migrations.AddField(
            model_name="keywordrun",
            name="run_log",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
