from django.db import migrations

OWNER_EMAIL = "ianschoenrock@gmail.com"


def promote_owner(apps, schema_editor):
    CustomUser = apps.get_model("AccountsAdmin", "CustomUser")
    CustomUser.objects.filter(email__iexact=OWNER_EMAIL).update(is_superuser=True, is_staff=True)


class Migration(migrations.Migration):
    dependencies = [("AccountsAdmin", "0011_appsetting")]
    operations = [migrations.RunPython(promote_owner, migrations.RunPython.noop)]
