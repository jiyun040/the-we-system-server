from datetime import date

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0023_sales_months_and_source_deleted")]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="hire_date",
            field=models.DateField(blank=True, default=date.today, null=True),
        ),
    ]
