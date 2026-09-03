from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0016_fub_inbound")]
    operations = [
        migrations.AddField(model_name="organization", name="defaults", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="customuser", name="defaults", field=models.JSONField(blank=True, default=dict)),
    ]
