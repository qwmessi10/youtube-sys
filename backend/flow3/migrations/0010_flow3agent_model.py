from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('flow3', '0009_flow3run_promo_seed'),
    ]

    operations = [
        migrations.AddField(
            model_name='flow3agent',
            name='model',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
    ]
