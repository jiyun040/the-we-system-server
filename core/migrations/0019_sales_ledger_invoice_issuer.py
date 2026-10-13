from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0018_sales_ledger_record")]
    operations = [
        migrations.AddField(
            model_name="salesledgerrecord",
            name="invoice_issuer",
            field=models.CharField(max_length=120, blank=True, default=""),
        ),
    ]
