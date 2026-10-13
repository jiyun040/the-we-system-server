from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0020_sales_invoice_issuer_default")]

    operations = [
        migrations.AddField(
            model_name="salesledgerrecord",
            name="adjustment_amount",
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="salesledgerrecord",
            name="adjustment_reason",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
