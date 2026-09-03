from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0014_deal_listing_agent")]
    operations = [
        migrations.AddField(model_name="deal", name="signed_re21_url", field=models.TextField(blank=True, null=True)),
    ]
