"""Developer / super-admin portal endpoints. Superuser only — this is the
owner's control panel (runtime settings, DocuSign environment, teams & users).
Team admins get their own, narrower version later."""
import os
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .docusign_service import DocuSignService
from .models import CustomUser, Organization, Deal
from .serializers import CustomUserSerializer, OrganizationSerializer
from .settings_service import all_settings, set_setting, DEFAULTS


class IsSuperuser(IsAuthenticated):
    def has_permission(self, request, view):
        return super().has_permission(request, view) and bool(getattr(request.user, "is_superuser", False))


def _docusign_status():
    out = {"current": DocuSignService.current_env(), "environments": {}}
    for env in ("demo", "production"):
        cfg = DocuSignService.env_config(env)
        out["environments"][env] = {
            "auth_server": cfg["auth_server"], "base_path": cfg["base_path"],
            "client_id_set": bool(cfg["client_id"]), "user_id_set": bool(cfg["user_id"]),
            "account_id_set": bool(cfg["account_id"]), "private_key_present": os.path.exists(cfg["private_key_path"]),
            "private_key_path": os.path.basename(cfg["private_key_path"]),
        }
        e = out["environments"][env]
        e["configured"] = all([e["client_id_set"], e["user_id_set"], e["account_id_set"], e["private_key_present"]])
    return out


class DevSettingsView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        return Response({"settings": all_settings(), "defaults": DEFAULTS, "docusign": _docusign_status(),
                         "server": {"debug": settings.DEBUG, "db_engine": settings.DATABASES["default"]["ENGINE"].rsplit(".", 1)[-1]}})

    def patch(self, request):
        updates = request.data.get("settings") or {}
        if not isinstance(updates, dict):
            return Response({"error": "settings must be an object"}, status=400)
        if "docusign_env" in updates and updates["docusign_env"] not in ("demo", "production"):
            return Response({"error": "docusign_env must be 'demo' or 'production'"}, status=400)
        if updates.get("docusign_env") == "production" and not _docusign_status()["environments"]["production"]["configured"]:
            return Response({"error": "Production DocuSign is not fully configured on the server (.env DOCUSIGN_PROD_* + private_key_prod.pem). Refusing to switch."}, status=400)
        for k, v in updates.items():
            set_setting(k, v, request.user)
        return Response({"settings": all_settings(), "docusign": _docusign_status()})


class DevDocuSignTestView(APIView):
    permission_classes = [IsSuperuser]

    def post(self, request):
        env = request.data.get("env") or DocuSignService.current_env()
        try:
            return Response(DocuSignService(env=env).test_connection())
        except Exception as e:
            return Response({"env": env, "error": str(e)}, status=502)


class DevTeamsView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        teams = []
        for org in Organization.objects.all().order_by("name"):
            d = OrganizationSerializer(org).data
            d["member_count"] = org.users.count()
            d["deal_count"] = Deal.objects.filter(agent__organization=org).count()
            teams.append(d)
        return Response(teams)

    def post(self, request):
        ser = OrganizationSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        org = ser.save()
        return Response(OrganizationSerializer(org).data, status=201)


class DevTeamDetailView(APIView):
    permission_classes = [IsSuperuser]

    def patch(self, request, pk):
        org = Organization.objects.filter(pk=pk).first()
        if org is None:
            return Response({"error": "Not found"}, status=404)
        ser = OrganizationSerializer(org, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=400)
        return Response(OrganizationSerializer(ser.save()).data)


class DevUsersView(APIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        users = CustomUser.objects.select_related("organization").order_by("organization__name", "last_name", "first_name")
        out = []
        for u in users:
            d = CustomUserSerializer(u).data
            d["organization_name"] = u.organization.name if u.organization else None
            d["deal_count"] = u.deals.count() if hasattr(u, "deals") else Deal.objects.filter(agent=u).count()
            d["fub_connected"] = bool(u.fub_access_token)
            d["is_active"] = u.is_active
            out.append(d)
        return Response(out)

    def post(self, request):
        data = dict(request.data)
        data = {k: (v[0] if isinstance(v, list) else v) for k, v in data.items()}
        email = (data.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required"}, status=400)
        if CustomUser.objects.filter(email__iexact=email).exists():
            return Response({"error": f"{email} already exists"}, status=400)
        org = Organization.objects.filter(pk=data.get("organization")).first() if data.get("organization") else None
        role = data.get("role") or "agent"
        if role not in dict(CustomUser.ROLE_CHOICES):
            return Response({"error": "invalid role"}, status=400)
        user = CustomUser.objects.create_user(
            email=email, organization=org,
            first_name=data.get("first_name", ""), last_name=data.get("last_name", ""),
            phone_number=(data.get("phone_number") or None), role=role,
        )
        return Response(CustomUserSerializer(user).data, status=201)


class DevUserDetailView(APIView):
    permission_classes = [IsSuperuser]

    def patch(self, request, pk):
        user = CustomUser.objects.filter(pk=pk).first()
        if user is None:
            return Response({"error": "Not found"}, status=404)
        d = request.data
        if "role" in d:
            if d["role"] not in dict(CustomUser.ROLE_CHOICES):
                return Response({"error": "invalid role"}, status=400)
            user.role = d["role"]
        if "organization" in d:
            user.organization = Organization.objects.filter(pk=d["organization"]).first() if d["organization"] else None
        for f in ("first_name", "last_name"):
            if f in d:
                setattr(user, f, d[f])
        if "phone_number" in d:
            user.phone_number = d["phone_number"] or None
        if "is_active" in d:
            if user.pk == request.user.pk and not d["is_active"]:
                return Response({"error": "You can't deactivate yourself."}, status=400)
            user.is_active = bool(d["is_active"])
        user.save()
        return Response(CustomUserSerializer(user).data)

    def delete(self, request, pk):
        user = CustomUser.objects.filter(pk=pk).first()
        if user is None:
            return Response({"error": "Not found"}, status=404)
        if user.pk == request.user.pk:
            return Response({"error": "You can't delete yourself."}, status=400)
        n = Deal.objects.filter(agent=user).count()
        if n and not request.data.get("confirm_deals"):
            return Response({"error": f"{user.email} owns {n} deal(s). Reassign them or pass confirm_deals=true to delete the deals too."}, status=409)
        user.delete()
        return Response(status=204)
