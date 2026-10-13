from django.db import migrations, models


def default_empty_issuers(apps, schema_editor):
    records = apps.get_model("core", "SalesLedgerRecord").objects.using(schema_editor.connection.alias)
    for record in records.only("pk", "invoice_issuer").iterator():
        if not record.invoice_issuer.strip():
            records.filter(pk=record.pk).update(invoice_issuer="협력사")


class Migration(migrations.Migration):
    dependencies = [("core", "0019_sales_ledger_invoice_issuer")]
    operations = [
        migrations.AlterField(model_name="salesledgerrecord", name="invoice_issuer",
                              field=models.CharField(max_length=120, default="협력사")),
        migrations.RunPython(default_empty_issuers, migrations.RunPython.noop),
    ]
