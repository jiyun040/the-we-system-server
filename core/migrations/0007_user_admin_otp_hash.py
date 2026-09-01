from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0006_grant_designated_admin_access")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="admin_otp_hash",
            field=models.CharField(blank=True, max_length=128),
        ),
    ]
