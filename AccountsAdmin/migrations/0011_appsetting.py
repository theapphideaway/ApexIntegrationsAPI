from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('AccountsAdmin', '0010_deal_acceptance_date_deal_checklist_state_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppSetting',
            fields=[
                ('key', models.CharField(max_length=100, primary_key=True, serialize=False)),
                ('value', models.JSONField(default=dict)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
