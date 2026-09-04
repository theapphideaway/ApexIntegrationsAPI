from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0018_dealdraft")]
    operations = [
        migrations.AddField(model_name="deal", name="send_key", field=models.CharField(blank=True, max_length=64, null=True, unique=True)),
        migrations.AddField(model_name="dealdocument", name="send_key", field=models.CharField(blank=True, max_length=64, null=True, unique=True)),
    ]
