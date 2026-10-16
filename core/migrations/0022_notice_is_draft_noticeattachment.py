import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0021_sales_adjustment")]

    operations = [
        migrations.AddField(
            model_name="notice",
            name="is_draft",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="NoticeAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("mime_type", models.CharField(default="application/octet-stream", max_length=150)),
                ("size", models.PositiveIntegerField()),
                ("base64_data", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("notice", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="core.notice")),
            ],
        ),
    ]
