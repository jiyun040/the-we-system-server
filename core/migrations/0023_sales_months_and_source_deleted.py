from django.db import migrations, models
import django.db.models.deletion


def preserve_billed_months(apps, schema_editor):
    Record = apps.get_model('core', 'SalesLedgerRecord')
    Month = apps.get_model('core', 'SalesLedgerMonth')
    fields = ('billing_date', 'invoice_date', 'deposit_date', 'invoice_issuer',
              'supply_amount', 'adjustment_amount', 'adjustment_reason', 'installment', 'note')
    alias = schema_editor.connection.alias
    for record in Record.objects.using(alias).filter(billing_date__isnull=False).iterator():
        month = max(record.start_date.replace(day=1), record.billing_date.replace(day=1))
        if record.end_date:
            month = min(month, record.end_date.replace(day=1))
        Month.objects.using(alias).get_or_create(
            record_id=record.pk, month=month,
            defaults={field: getattr(record, field) for field in fields},
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0022_notice_is_draft_noticeattachment')]
    operations = [
        migrations.AddField(model_name='salesledgerrecord', name='source_deleted', field=models.BooleanField(default=False)),
        migrations.CreateModel(
            name='SalesLedgerMonth',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('month', models.DateField()),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('billing_date', models.DateField(blank=True, null=True)),
                ('invoice_date', models.DateField(blank=True, null=True)),
                ('deposit_date', models.DateField(blank=True, null=True)),
                ('invoice_issuer', models.CharField(default='협력사', max_length=120)),
                ('supply_amount', models.PositiveBigIntegerField(default=0)),
                ('adjustment_amount', models.PositiveBigIntegerField(default=0)),
                ('adjustment_reason', models.CharField(blank=True, max_length=500)),
                ('installment', models.PositiveSmallIntegerField(default=1)),
                ('status', models.CharField(blank=True, max_length=20)),
                ('note', models.CharField(blank=True, max_length=500)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='months', to='core.salesledgerrecord')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('record', 'month'), name='unique_sales_record_month')]},
        ),
        migrations.RunPython(preserve_billed_months, migrations.RunPython.noop),
    ]
