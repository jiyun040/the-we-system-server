from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0025_sales_record_date")]

    operations = [
        migrations.CreateModel(
            name="SalesLedgerArchive",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveSmallIntegerField(db_index=True, unique=True)),
                ("file", models.FileField(upload_to="sales-ledger-archives/")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
