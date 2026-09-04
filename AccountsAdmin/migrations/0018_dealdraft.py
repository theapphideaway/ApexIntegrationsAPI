import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0017_contract_defaults")]
    operations = [
        migrations.CreateModel(
            name="DealDraft",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(blank=True, default="", max_length=255)),
                ("source", models.CharField(blank=True, default="", max_length=20)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("device", models.CharField(blank=True, default="", max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drafts", to=settings.AUTH_USER_MODEL)),
                ("revising_deal", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="revision_drafts", to="AccountsAdmin.deal")),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
