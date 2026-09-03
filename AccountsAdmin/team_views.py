"""Team-admin portal endpoints: a team admin manages THEIR OWN team only —
members, roles, invitations, deactivation. Everything is scoped to
request.user.organization; cross-team access is impossible by construction.
The platform owner (superuser) can also use these on any team via ?team=<id>."""
from django.conf import settings
from django.core.mail import send_mail
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CustomUser, Organization, Deal
from .serializers import CustomUserSerializer, OrganizationSerializer
from . import defaults_service


class IsTeamAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        u = request.user
        return bool(getattr(u, "is_superuser", False)) or getattr(u, "role", "") == "admin"


def team_for(request):
    """The organization this request may manage, or None."""
    u = request.user
    if getattr(u, "is_superuser", False) and request.query_params.get("team"):
        return Organization.objects.filter(pk=request.query_params.get("team")).first()
    return u.organization if getattr(u, "organization_id", None) else None


def member_payload(u):
    d = CustomUserSerializer(u).data
    d.pop("docusign_production", None)   # dev-portal concern, not the team's
    d["deal_count"] = Deal.objects.filter(agent=u).count()
    d["fub_connected"] = bool(u.fub_access_token)
    d["is_active"] = u.is_active
    return d


class TeamView(APIView):
    """GET /api/team/ — the admin's team + its members."""
    permission_classes = [IsTeamAdmin]

    def get(self, request):
        org = team_for(request)
        if org is None:
            return Response({"error": "You are not on a team."}, status=400)
        members = org.users.order_by("last_name", "first_name")
        return Response({
            "team": OrganizationSerializer(org).data,
            "members": [member_payload(u) for u in members],
            "deal_count": Deal.objects.filter(agent__organization=org).count(),
        })

    def patch(self, request):
        """Rename the team."""
        org = team_for(request)
        if org is None:
            return Response({"error": "You are not on a team."}, status=400)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "name is required"}, status=400)
        org.name = name[:255]
        org.save(update_fields=["name"])
        return Response(OrganizationSerializer(org).data)


class TeamMembersView(APIView):
    """POST /api/team/members/ — invite someone onto the team."""
    permission_classes = [IsTeamAdmin]

    def post(self, request):
        org = team_for(request)
        if org is None:
            return Response({"error": "You are not on a team."}, status=400)
        d = request.data
        email = (d.get("email") or "").strip().lower()
        if not email:
            return Response({"error": "email is required"}, status=400)
        if CustomUser.objects.filter(email__iexact=email).exists():
            return Response({"error": f"{email} already has an account."}, status=400)
        role = d.get("role") or "agent"
        if role not in dict(CustomUser.ROLE_CHOICES):
            return Response({"error": "invalid role"}, status=400)
        user = CustomUser.objects.create_user(
            email=email, organization=org,
            first_name=(d.get("first_name") or "").strip(), last_name=(d.get("last_name") or "").strip(),
            phone_number=(d.get("phone_number") or "").strip() or None, role=role,
        )
        # Invitation — best effort; the account works regardless.
        try:
            send_mail(
                subject=f"You've been added to {org.name} on Apex Deal Desk",
                message=(f"Hi {user.first_name or ''},\n\n{request.user.first_name} {request.user.last_name} added you to "
                         f"{org.name}.\n\nLog in with this email address — a one-time code is emailed to you each time:\n"
                         f"  Web: https://www.apexintegrations.ai/portal/\n  iPhone: the Real Estate AI app\n\n"
                         f"Your role: {dict(CustomUser.ROLE_CHOICES)[role]}\n"),
                from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email], fail_silently=True,
            )
        except Exception as e:
            print(f"Invite email failed (non-fatal): {e}")
        return Response(member_payload(user), status=201)


class TeamMemberDetailView(APIView):
    """PATCH /api/team/members/<id>/ — role, name, phone, active. Only members
    of the admin's own team; never a superuser; never yourself for deactivate."""
    permission_classes = [IsTeamAdmin]

    def _member(self, request, pk):
        org = team_for(request)
        if org is None:
            return None
        return org.users.filter(pk=pk).first()

    def patch(self, request, pk):
        user = self._member(request, pk)
        if user is None:
            return Response({"error": "Not found on your team."}, status=404)
        if user.is_superuser and not request.user.is_superuser:
            return Response({"error": "That account can't be changed from here."}, status=403)
        d = request.data
        if "role" in d:
            if d["role"] not in dict(CustomUser.ROLE_CHOICES):
                return Response({"error": "invalid role"}, status=400)
            if user.pk == request.user.pk and d["role"] != "admin":
                return Response({"error": "You can't remove your own admin role."}, status=400)
            user.role = d["role"]
        for f in ("first_name", "last_name"):
            if f in d:
                setattr(user, f, (d[f] or "").strip())
        if "phone_number" in d:
            user.phone_number = (d["phone_number"] or "").strip() or None
        if "is_active" in d:
            if user.pk == request.user.pk and not d["is_active"]:
                return Response({"error": "You can't deactivate yourself."}, status=400)
            user.is_active = bool(d["is_active"])
        user.save()
        return Response(member_payload(user))


class TeamDefaultsView(APIView):
    """GET   /api/team/defaults/ → {defaults}
    PATCH /api/team/defaults/ {defaults: {key: value | null}} — merge; null removes
    (and unlocks) a key. Every key present is locked for the team's agents."""
    permission_classes = [IsTeamAdmin]

    def get(self, request):
        org = team_for(request)
        if org is None:
            return Response({"error": "You are not on a team."}, status=400)
        return Response({"defaults": org.defaults or {}, "locked": sorted((org.defaults or {}).keys())})

    def patch(self, request):
        org = team_for(request)
        if org is None:
            return Response({"error": "You are not on a team."}, status=400)
        updates = request.data.get("defaults")
        if not isinstance(updates, dict):
            return Response({"error": "defaults must be an object"}, status=400)
        current = dict(org.defaults or {})
        for k, v in updates.items():
            if k in defaults_service.NEVER_DEFAULT:
                continue
            if v in (None, "", [], {}):
                current.pop(k, None)
            else:
                current[k] = v
        org.defaults = current
        org.save(update_fields=["defaults"])
        return Response({"defaults": current, "locked": sorted(current.keys())})
