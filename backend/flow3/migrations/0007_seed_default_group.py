from django.db import migrations


def seed_default_group(apps, schema_editor):
    """建「默认分组」并把存量未分组的 hook 素材归入默认分组。"""
    Group = apps.get_model("flow3", "Flow3MaterialGroup")
    Material = apps.get_model("flow3", "Flow3Material")
    default, _ = Group.objects.get_or_create(name="默认分组", defaults={"is_default": True})
    if not default.is_default:
        default.is_default = True
        default.save(update_fields=["is_default"])
    # 存量 hook 素材无分组的归入默认分组。
    Material.objects.filter(material_type="hook", group__isnull=True).update(group=default)


def remove_default_group(apps, schema_editor):
    Group = apps.get_model("flow3", "Flow3MaterialGroup")
    Group.objects.filter(name="默认分组", is_default=True).delete()


class Migration(migrations.Migration):
    dependencies = [("flow3", "0006_flow3materialgroup_flow3run_finished_at_and_more")]

    operations = [migrations.RunPython(seed_default_group, remove_default_group)]
