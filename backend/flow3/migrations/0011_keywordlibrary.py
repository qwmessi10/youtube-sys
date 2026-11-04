# Generated migration for 关键词库
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("flow3", "0010_flow3agent_model"),
    ]

    operations = [
        migrations.CreateModel(
            name="KeywordLibrary",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keyword", models.CharField(max_length=255, verbose_name="关键词")),
                ("search_volume", models.IntegerField(default=0, verbose_name="搜索量（权重）")),
                ("language", models.CharField(choices=[("en", "英语"), ("pt", "葡萄牙语"), ("ru", "俄语"), ("hi", "印地语"), ("es", "西班牙语"), ("other", "其他")], default="en", max_length=16, verbose_name="语言")),
                ("source", models.CharField(choices=[("primary", "主词库（带权重）"), ("suggest", "长尾词")], default="primary", max_length=16, verbose_name="来源")),
                ("enabled", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "关键词库",
                "verbose_name_plural": "关键词库",
                "ordering": ["-search_volume", "id"],
            },
        ),
    ]
