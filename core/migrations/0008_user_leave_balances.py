from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0007_user_admin_otp_hash")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="annual_leave_days",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="monthly_leave_days",
            field=models.DecimalField(
                blank=True,
                decimal_places=1,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="leave_balance_adjustment",
            field=models.DecimalField(
                decimal_places=1,
                default=Decimal("0"),
                max_digits=6,
            ),
        ),
    ]
