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
        for deal in Deal.objects.filter(agent=user, fub_synced=False):
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
