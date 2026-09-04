from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0019_send_key")]
    operations = [
        migrations.AddField(model_name="deal", name="is_test", field=models.BooleanField(default=False)),
    ]
