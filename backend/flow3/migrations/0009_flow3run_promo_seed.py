from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flow3', '0008_sync_agent_prompts'),
    ]

    operations = [
        migrations.AddField(
            model_name='flow3run',
            name='promo_seed',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
