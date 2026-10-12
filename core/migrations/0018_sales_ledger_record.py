# Generated manually for the ERP sales ledger feature.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0017_restore_legacy_designated_admin_access")]

    operations = [
        migrations.AlterField(
            model_name="portalsetting",
            name="portal_name",
            field=models.CharField(default="우리기술 ERP", max_length=100),
        ),
        migrations.CreateModel(
            name="SalesLedgerRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_id", models.CharField(db_index=True, max_length=100, unique=True)),
                ("project_name", models.CharField(db_index=True, max_length=255)),
                ("contractor", models.CharField(blank=True, max_length=120)),
                ("partner", models.CharField(blank=True, max_length=120)),
                ("elevator", models.CharField(blank=True, max_length=100)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("pdam_status", models.CharField(blank=True, max_length=40)),
                ("source_category", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=20)),
                ("billing_date", models.DateField(blank=True, null=True)),
                ("invoice_date", models.DateField(blank=True, null=True)),
                ("deposit_date", models.DateField(blank=True, null=True)),
                ("supply_amount", models.PositiveBigIntegerField(default=0)),
                ("installment", models.PositiveSmallIntegerField(default=1)),
                ("status", models.CharField(default="신규", max_length=20)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("source_updated_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["project_name", "elevator", "id"]},
        )
    ]
