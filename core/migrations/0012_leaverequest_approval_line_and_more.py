from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_approvalformtemplate_approval_lines"),
    ]

    operations = [
        migrations.AddField(
            model_name="leaverequest",
            name="approval_line",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="portalsetting",
            name="leave_approval_lines",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
