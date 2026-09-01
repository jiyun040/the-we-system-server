from django.db import migrations, models


DEFAULT_DEPARTMENT_ORDER = [
    "대표이사",
    "기술부",
    "연구소",
    "관리부",
    "공무",
    "경리부",
]


def initialize_department_sort_order(apps, schema_editor):
    department = apps.get_model("core", "Department")
    rows = list(department.objects.all())
    preferred = {name: index for index, name in enumerate(DEFAULT_DEPARTMENT_ORDER)}
    rows.sort(
        key=lambda row: (
            0 if row.name in preferred else 1,
            preferred.get(row.name, 0),
            row.name,
        )
    )
    for index, row in enumerate(rows):
        row.sort_order = index
    department.objects.bulk_update(rows, ["sort_order"])


class Migration(migrations.Migration):
    dependencies = [("core", "0004_grant_kim_hyomin_admin_access")]

    operations = [
        migrations.AddField(
            model_name="department",
            name="sort_order",
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.RunPython(
            initialize_department_sort_order,
            migrations.RunPython.noop,
        ),
        migrations.AlterModelOptions(
            name="department",
            options={"ordering": ["sort_order", "name"]},
        ),
    ]
