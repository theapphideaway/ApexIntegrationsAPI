"""
Follow Up Boss integration.

The app never talks to FUB directly: it asks Django for a connect URL, the
agent signs in via Safari, FUB redirects to our callback, and Django stores
the tokens on the agent's user row. Document sync then happens entirely
server-side — at packet send and at DocuSign completion — using the buyer's
real contact info.
"""
import urllib.parse

import requests
from django.conf import settings
from django.core import signing

FUB_AUTHORIZE_URL = "https://app.followupboss.com/oauth/authorize"
FUB_TOKEN_URL = "https://app.followupboss.com/oauth/token"
FUB_API = "https://api.followupboss.com/v1"
REQUEST_TIMEOUT = 15  # seconds — a slow CRM must never hang a uWSGI worker
REDIRECT_URI = "https://www.apexintegrations.ai/api/auth/fub/callback/"

# Signed-state protection: the state parameter proves the callback belongs to
# the agent who started the flow, so nobody can bind their FUB account to
# someone else's Apex account by forging the user id.
STATE_SALT = "fub-oauth-state"
STATE_MAX_AGE = 60 * 15  # the agent has 15 minutes to finish signing in


def make_connect_url(user) -> str:
    state = signing.dumps({"uid": str(user.id)}, salt=STATE_SALT)
    params = urllib.parse.urlencode({
        "client_id": settings.FUB_CLIENT_ID.strip(),
        "response_type": "auth_code",
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "prompt": "login",
    })
    return f"{FUB_AUTHORIZE_URL}?{params}"


def user_id_from_state(state: str) -> str:
    """Raises signing.BadSignature / SignatureExpired on tampering or timeout."""
    return signing.loads(state, salt=STATE_SALT, max_age=STATE_MAX_AGE)["uid"]


def exchange_code(code: str, state: str) -> dict:
    """Exchanges the auth code for tokens. FUB quirk: the state must be echoed
    back in the token request."""
    response = requests.post(
        FUB_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": REDIRECT_URI,
            "state": state.strip(),
        },
        auth=(settings.FUB_CLIENT_ID.strip(), settings.FUB_CLIENT_SECRET.strip()),
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _refresh(user) -> bool:
    """Tries to refresh the agent's FUB access token. Returns True on success;
    clears the stored tokens (disconnected) when the refresh is rejected."""
    if not user.fub_refresh_token:
        return False
    response = requests.post(
        FUB_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": user.fub_refresh_token},
        auth=(settings.FUB_CLIENT_ID.strip(), settings.FUB_CLIENT_SECRET.strip()),
        timeout=REQUEST_TIMEOUT,
    )
    if response.status_code != 200:
        user.fub_access_token = None
        user.fub_refresh_token = None
        user.save(update_fields=["fub_access_token", "fub_refresh_token"])
        return False
    data = response.json()
    user.fub_access_token = data.get("access_token")
    if data.get("refresh_token"):
        user.fub_refresh_token = data["refresh_token"]
    user.save(update_fields=["fub_access_token", "fub_refresh_token"])
    return True


def _headers(user) -> dict:
    return {
        "Authorization": f"Bearer {user.fub_access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-System": "Docu-Flow-AI",
    }


def _request(user, method: str, url: str, **kwargs):
    """FUB request with one automatic token refresh on 401."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    response = requests.request(method, url, headers=_headers(user), **kwargs)
    if response.status_code == 401 and _refresh(user):
        response = requests.request(method, url, headers=_headers(user), **kwargs)
    return response


def _find_or_create_person(user, name: str, email: str, phone: str = ""):
    """Returns the FUB person id for the buyer, creating the contact if new."""
    if email:
        res = _request(user, "GET", f"{FUB_API}/people?email={urllib.parse.quote(email)}")
        if res.status_code == 200:
            people = res.json().get("people", [])
            if people:
                return people[0]["id"]

    name_parts = (name or "Unknown Client").split(" ", 1)
    payload = {"firstName": name_parts[0], "source": "Apex Integrations AI"}
    if len(name_parts) > 1:
        payload["lastName"] = name_parts[1]
    if email:
        payload["emails"] = [{"value": email}]
    if phone:
        payload["phones"] = [{"value": phone}]

    res = _request(user, "POST", f"{FUB_API}/people", json=payload)
    if res.status_code in (200, 201):
        return res.json().get("id")
    return None


def backfill_deals(user) -> int:
    """Posts a catch-up note for every one of the agent's deals that has never
    been synced. Runs after a successful FUB connect, so the CRM reflects the
    existing pipeline, not just deals created after connecting. Returns the
    number of deals synced. Never raises."""
    from django.core.files.storage import default_storage
    from .models import Deal

    synced = 0
    try:
        for deal in Deal.objects.filter(agent=user, fub_synced=False, is_test=False):
            if deal.status == 'fully_executed':
                subject = f"Contract fully executed — {deal.property_address}"
                doc_key = deal.signed_pdf_url
                line = "all parties have signed."
            else:
                subject = f"Offer packet — {deal.property_address} ({deal.get_status_display()})"
                doc_key = deal.draft_pdf_url or deal.signed_pdf_url
                line = f"current status: {deal.get_status_display()}."

            link_html = ""
            if doc_key:
                try:
                    link_html = f'<p>📄 <a href="{default_storage.url(doc_key)}" target="_blank">View the packet</a></p>'
                except Exception:
                    pass

            ok = sync_document(
                user,
                buyer_name=deal.buyer_names,
                buyer_email=deal.buyer_email or "",
                subject=subject,
                body_html=(
                    f"<p><strong>Apex Integrations AI</strong>: {line}</p>"
                    f"<p>Property: {deal.property_address}<br>Buyer(s): {deal.buyer_names}</p>{link_html}"
                ),
            )
            if ok:
                deal.fub_synced = True
                deal.save(update_fields=["fub_synced"])
                synced += 1
    except Exception as e:
        print(f"FUB backfill failed (non-fatal): {e}")
    return synced


def sync_document(user, buyer_name: str, buyer_email: str, subject: str,
                  body_html: str, buyer_phone: str = "") -> bool:
    """Attaches a note to the buyer's FUB timeline. Returns False (never
    raises) when the agent isn't connected or FUB rejects the call — document
    sync must never break the deal flow."""
    try:
        if not user.fub_access_token:
            return False
        person_id = _find_or_create_person(user, buyer_name, buyer_email, buyer_phone)
        if not person_id:
            print(f"FUB sync: could not find/create contact for {buyer_email}")
            return False
        res = _request(user, "POST", f"{FUB_API}/notes", json={
            "personId": person_id,
            "subject": subject,
            "body": body_html,
            "isHtml": True,
        })
        ok = res.status_code in (200, 201)
        if not ok:
            print(f"FUB sync: note rejected ({res.status_code}): {res.text[:200]}")
        return ok
    except Exception as e:
        print(f"FUB sync failed (non-fatal): {e}")
        return False


# ---------------------------------------------------------------------------
# Inbound: FUB → app. Webhooks are per FUB ACCOUNT (a team shares one), with a
# hard limit of two per event, so we register once per account and put a
# signed account token in the URL. Payloads carry ids only; we fetch the
# resource with any connected user's token, find the person, and match the
# deal by the buyer's email.
# ---------------------------------------------------------------------------
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone

WEBHOOK_EVENTS = [
    "notesCreated", "tasksCreated", "tasksUpdated", "appointmentsCreated",
    "callsCreated", "textMessagesCreated", "emailsCreated",
    "dealsCreated", "dealsUpdated", "peopleStageUpdated",
]
WEBHOOK_SALT = "fub-webhook-account"


def fetch_account_id(user) -> str:
    """The FUB account behind this user's token (GET /v1/identity, else /v1/me)."""
    for path in ("/identity", "/me"):
        try:
            res = _request(user, "GET", f"{FUB_API}{path}")
            if res.status_code != 200:
                continue
            j = res.json()
            acct = j.get("account") if isinstance(j.get("account"), dict) else None
            for candidate in ((acct or {}).get("id"), j.get("accountId"), j.get("account_id"), j.get("account")):
                if candidate not in (None, "", {}) and not isinstance(candidate, dict):
                    return str(candidate)
        except Exception as e:
            print(f"FUB identity lookup failed via {path}: {e}")
    return ""


def webhook_url(account_id: str) -> str:
    token = signing.dumps({"acct": account_id}, salt=WEBHOOK_SALT)
    return f"https://www.apexintegrations.ai/api/auth/fub/webhook/{token}/"


def account_from_webhook_token(token: str) -> str:
    return signing.loads(token, salt=WEBHOOK_SALT)["acct"]   # no max_age: the URL lives in FUB


def ensure_webhooks(user) -> dict:
    """Register our listener for every event we consume, once per account.
    Reuses existing registrations (FUB allows only two per event per system).
    Returns {event: 'existing'|'created'|'failed:<reason>'}."""
    out = {}
    if not user.fub_access_token:
        return {"error": "not connected"}
    if not user.fub_account_id:
        user.fub_account_id = fetch_account_id(user)
        if user.fub_account_id:
            user.save(update_fields=["fub_account_id"])
    if not user.fub_account_id:
        return {"error": "could not determine the FUB account id"}
    url = webhook_url(user.fub_account_id)
    existing = {}
    try:
        res = _request(user, "GET", f"{FUB_API}/webhooks")
        if res.status_code == 200:
            for w in res.json().get("webhooks", []):
                if w.get("url") == url:
                    existing[w.get("event")] = w
    except Exception as e:
        print(f"FUB webhook list failed: {e}")
    for event in WEBHOOK_EVENTS:
        if event in existing:
            out[event] = "existing"
            continue
        try:
            res = _request(user, "POST", f"{FUB_API}/webhooks", json={"event": event, "url": url})
            out[event] = "created" if res.status_code in (200, 201) else f"failed:{res.status_code} {res.text[:80]}"
        except Exception as e:
            out[event] = f"failed:{e}"
    return out


def verify_signature(raw_body: bytes, signature: str) -> bool:
    """FUB-Signature = HMAC-SHA256(base64(body), X-System-Key). If no system
    key is configured we can't verify — the signed URL token is the gate."""
    key = (getattr(settings, "FUB_SYSTEM_KEY", "") or "").strip()
    if not key:
        return True
    if not signature:
        return False
    digest = hmac.new(key.encode(), base64.b64encode(raw_body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature.strip())


def _person_ids_from_resource(event: str, resource: dict) -> list:
    if event == "peopleStageUpdated":
        return [resource.get("id")] if resource.get("id") else []
    ids = []
    if resource.get("personId"):
        ids.append(resource["personId"])
    for key in ("people", "persons"):
        for p in resource.get(key) or []:
            pid = p.get("id") if isinstance(p, dict) else p
            if pid:
                ids.append(pid)
    for key in ("personIds", "invitees"):
        for p in resource.get(key) or []:
            pid = p.get("personId") if isinstance(p, dict) else p
            if pid:
                ids.append(pid)
    return [i for i in dict.fromkeys(ids)]


def _person_emails(user, person_id) -> list:
    res = _request(user, "GET", f"{FUB_API}/people/{person_id}")
    if res.status_code != 200:
        return []
    return [(e.get("value") or "").strip().lower() for e in res.json().get("emails", []) if e.get("value")]


def _summarize(event: str, resource: dict) -> tuple:
    """(title, body, actor) for the activity feed."""
    kind = event.replace("Created", "").replace("Updated", "")
    who = resource.get("createdBy") or resource.get("userName") or resource.get("assignedUserName") or ""
    if isinstance(who, dict):
        who = who.get("name", "")
    if kind == "notes":
        return (resource.get("subject") or "Note added", resource.get("body") or "", who)
    if kind == "tasks":
        state = "completed" if resource.get("isCompleted") else ("updated" if "Updated" in event else "created")
        due = resource.get("dueDate") or ""
        return (f"Task {state}: {resource.get('name') or ''}".strip(), f"Due {due}" if due else "", who)
    if kind == "appointments":
        return (f"Appointment: {resource.get('title') or ''}".strip(), f"{resource.get('start') or ''} {resource.get('location') or ''}".strip(), who)
    if kind == "calls":
        return (f"Call ({resource.get('outcome') or 'logged'})", resource.get("note") or "", who)
    if kind == "textMessages":
        return ("Text message" + (" sent" if resource.get("isIncoming") is False else " received"), resource.get("message") or "", who)
    if kind == "emails":
        return (f"Email: {resource.get('subject') or ''}".strip(), "", who)
    if kind == "deals":
        return (f"FUB deal {'updated' if 'Updated' in event else 'created'}: {resource.get('name') or ''}".strip(),
                f"Stage: {resource.get('stageName') or resource.get('stage') or ''}".strip(), who)
    if kind == "peopleStage":
        return (f"Stage changed: {resource.get('stage') or ''}".strip(), "", who)
    return (event, "", who)


def process_webhook(account_id: str, payload: dict) -> int:
    """Turn one FUB event into DealActivity rows. Returns rows created."""
    from .models import CustomUser, Deal, DealActivity
    event = payload.get("event") or ""
    ids = payload.get("resourceIds") or []
    if not event or not ids:
        return 0
    users = list(CustomUser.objects.filter(fub_account_id=account_id).exclude(fub_access_token__isnull=True).exclude(fub_access_token=""))
    if not users:
        return 0
    org_ids = {u.organization_id for u in users if u.organization_id}
    user = users[0]
    created = 0
    kind = event.replace("Created", "").replace("Updated", "").replace("Deleted", "")
    path = {"peopleStage": "people"}.get(kind, kind)
    when = payload.get("eventCreated")
    try:
        occurred = datetime.fromisoformat(str(when).replace("Z", "+00:00")) if when else datetime.now(dt_timezone.utc)
    except ValueError:
        occurred = datetime.now(dt_timezone.utc)
    for rid in ids[:20]:
        external_id = f"{event}:{rid}"
        if DealActivity.objects.filter(external_id=external_id).exists():
            continue
        try:
            res = _request(user, "GET", f"{FUB_API}/{path}/{rid}")
            if res.status_code != 200:
                continue
            resource = res.json()
        except Exception as e:
            print(f"FUB resource fetch failed {path}/{rid}: {e}")
            continue
        emails = set()
        for pid in _person_ids_from_resource(event, resource)[:5]:
            emails.update(_person_emails(user, pid))
        if not emails:
            continue
        deals = Deal.objects.filter(buyer_email__in=list(emails), agent__organization_id__in=org_ids, is_archived=False)
        if not deals.exists():
            continue
        title, body, actor = _summarize(event, resource)
        for i, deal in enumerate(deals[:5]):
            DealActivity.objects.get_or_create(
                external_id=external_id if i == 0 else f"{external_id}:{deal.id}",
                defaults={"deal": deal, "source": "fub", "kind": event, "title": title[:255], "body": body[:5000],
                          "actor": str(actor)[:150], "external_url": payload.get("uri") or "", "occurred_at": occurred},
            )
            created += 1
    return created
