from django.db import migrations


def seed_department_rooms(apps, schema_editor):
    Department = apps.get_model("core", "Department")
    User = apps.get_model("core", "User")
    SharedRoom = apps.get_model("core", "SharedRoom")

    creator = (
        User.objects.filter(username="admin", is_active=True).first()
        or User.objects.filter(is_staff=True, is_active=True).first()
        or User.objects.filter(is_active=True).first()
    )
    if creator is None:
        return

    for department in Department.objects.all():
        room, created = SharedRoom.objects.get_or_create(
            name=department.name,
            defaults={"creator_id": creator.pk},
        )
        if created:
            room.members.set(
                User.objects.filter(department_id=department.pk, is_active=True)
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0030_remove_salesledgerreportmonth_unique_sales_report_month_and_more")]
    operations = [migrations.RunPython(seed_department_rooms, migrations.RunPython.noop)]
