from django.db import migrations, models


def backfill_record_date(apps, schema_editor):
    Record = apps.get_model("core", "SalesLedgerRecord")
    Record.objects.filter(record_date__isnull=True).update(
        record_date=models.F("start_date")
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0024_user_hire_date_optional")]

    operations = [
        migrations.AddField(
            model_name="salesledgerrecord",
            name="record_date",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(backfill_record_date, migrations.RunPython.noop),
    ]
