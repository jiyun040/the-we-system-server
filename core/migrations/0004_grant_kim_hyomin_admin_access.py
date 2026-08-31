from django.db import migrations


def grant_kim_hyomin_admin_access(apps, schema_editor):
    user = apps.get_model("core", "User")
    user.objects.filter(
        username__iexact="we061046",
        first_name="김효민",
        is_active=True,
    ).update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0003_restore_default_approval_forms")]

    operations = [
        migrations.RunPython(
            grant_kim_hyomin_admin_access,
            migrations.RunPython.noop,
        ),
    ]
