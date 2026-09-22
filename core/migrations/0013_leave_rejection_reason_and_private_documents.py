from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0012_leaverequest_approval_line_and_more")]

    operations = [
        migrations.AddField(
            model_name="leaverequest",
            name="rejection_reason",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AlterField(
            model_name="approvaldocument",
            name="department_visible",
            field=models.BooleanField(default=False),
        ),
    ]
