from django.db import migrations


def set_designated_admin_access(apps, schema_editor):
    user = apps.get_model("core", "User")
    user.objects.filter(
        username__in=["we81048", "we061046"],
        first_name="김효민",
        department__name="경리부",
        position="대리",
        is_active=True,
    ).update(is_staff=False)
    user.objects.filter(
        username__iexact="we81049",
        first_name="김효민",
        department__name="경리부",
        position="대리",
        is_active=True,
    ).update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0016_material_purchase_form")]

    operations = [
        migrations.RunPython(
            set_designated_admin_access,
            migrations.RunPython.noop,
        ),
    ]
