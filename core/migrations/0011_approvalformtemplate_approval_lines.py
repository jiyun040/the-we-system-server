from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_remove_user_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalformtemplate",
            name="approval_lines",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
