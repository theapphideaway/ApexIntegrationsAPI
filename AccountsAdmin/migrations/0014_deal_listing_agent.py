from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0013_docusign_env")]
    operations = [
        migrations.AddField(model_name="deal", name="listing_agent_email", field=models.EmailField(blank=True, null=True)),
        migrations.AddField(model_name="deal", name="listing_agent_name", field=models.CharField(blank=True, default="", max_length=150)),
    ]
