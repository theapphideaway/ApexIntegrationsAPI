"""Runtime settings (DB-backed, dev-portal editable). Values are JSON; a
missing row returns the default. Never store secrets here."""
from .models import AppSetting

DEFAULTS = {
    "docusign_env": "demo",          # "demo" | "production"
}


def get_setting(key, default=None):
    try:
        return AppSetting.objects.get(pk=key).value
    except AppSetting.DoesNotExist:
        return DEFAULTS.get(key, default)
    except Exception:
        return DEFAULTS.get(key, default)


def set_setting(key, value, user=None):
    obj, _ = AppSetting.objects.update_or_create(pk=key, defaults={"value": value, "updated_by": user})
    return obj


def all_settings():
    out = dict(DEFAULTS)
    out.update({s.key: s.value for s in AppSetting.objects.all()})
    return out
