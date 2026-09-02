from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_notice"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="user",
            name="email",
        ),
        migrations.AlterModelManagers(
            name="user",
            managers=[],
        ),
    ]
