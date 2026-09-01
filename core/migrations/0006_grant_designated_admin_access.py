from django.db import migrations


def grant_designated_admin_access(apps, schema_editor):
    user = apps.get_model("core", "User")
    user.objects.filter(
        username__iexact="we81048",
        first_name="김효민",
        department__name="경리부",
        position="대리",
        is_active=True,
    ).update(is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0005_department_sort_order")]

    operations = [
        migrations.RunPython(
            grant_designated_admin_access,
            migrations.RunPython.noop,
        ),
    ]
