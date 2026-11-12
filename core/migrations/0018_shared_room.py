from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("core", "0017_restore_legacy_designated_admin_access")]
    operations = [
        migrations.CreateModel(
            name="SharedRoom",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("creator", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="shared_rooms_created", to="core.user")),
                ("members", models.ManyToManyField(blank=True, related_name="shared_rooms", to="core.user")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddField(
            model_name="boardpost", name="room",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="posts", to="core.sharedroom"),
        ),
    ]
