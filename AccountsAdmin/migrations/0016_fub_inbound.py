from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0015_deal_signed_re21_url")]
    operations = [
        migrations.AddField(model_name="customuser", name="fub_account_id", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.CreateModel(
            name="DealActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("fub", "Follow Up Boss"), ("app", "App")], default="fub", max_length=10)),
                ("kind", models.CharField(max_length=40)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField(blank=True, default="")),
                ("actor", models.CharField(blank=True, default="", max_length=150)),
                ("external_id", models.CharField(max_length=120, unique=True)),
                ("external_url", models.TextField(blank=True, default="")),
                ("occurred_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("deal", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activities", to="AccountsAdmin.deal")),
            ],
            options={"ordering": ["-occurred_at"]},
        ),
    ]
