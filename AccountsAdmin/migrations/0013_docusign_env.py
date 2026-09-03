from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0012_owner_superuser")]
    operations = [
        migrations.AddField(model_name="customuser", name="docusign_production", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="deal", name="docusign_env", field=models.CharField(default="demo", max_length=12)),
        migrations.AddField(model_name="dealdocument", name="docusign_env", field=models.CharField(default="demo", max_length=12)),
    ]
