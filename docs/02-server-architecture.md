# 02 · Server Architecture (Django REST API)

Repo: `ApexIntegrationsAPI/`. Django 4.2 + Django REST Framework + SimpleJWT. Python 3.11 on PythonAnywhere.
Single app: `AccountsAdmin/`. Project settings/urls: `ApexIntegrationsAPI/`.

## Module map

| File | Responsibility |
|---|---|
| `AccountsAdmin/models.py` | `Organization` (team), `CustomUser`, `OTPCode`, `Deal`, `DealDocument`, `AppSetting`, `DealActivity` |
| `AccountsAdmin/views.py` | Auth/OTP, users/orgs (admin), deals, deal state, documents, packet preview/send, DocuSign webhook + status + distribute, MLS proxy, FUB OAuth/webhooks, `portal_index`, visibility helpers (`deals_for`, `is_team_role`) |
| `AccountsAdmin/team_views.py` | Team-admin API (own team only): members, invites, team defaults |
| `AccountsAdmin/dev_views.py` | Superuser API: runtime settings, DocuSign env test, all teams/users |
| `AccountsAdmin/serializers.py` | `DealSerializer` (presigned URLs, agent name/team), `DealDocumentSerializer`, `CustomUserSerializer` (exposes `is_superuser`, `docusign_env`) |
| `AccountsAdmin/pdf_service.py` | `PDFGenerationService(doc_type)` + `DocumentType` constants; one `_map_<form>` per template mapping JSON keys → AcroForm field names; stamps DocuSign anchor strings |
| `AccountsAdmin/docusign_service.py` | JWT auth per environment, `send_bundle_envelope` (anchor tabs), `send_pdf_envelope` (positional tabs for received PDFs), `void_envelope`, `download_envelope_document`, `test_connection`, `env_for_user` |
| `AccountsAdmin/fub_service.py` | FUB OAuth, notes out (`sync_document`, `backfill_deals`), inbound webhooks (`ensure_webhooks`, `verify_signature`, `process_webhook`) |
| `AccountsAdmin/defaults_service.py` | Team/agent contract defaults: precedence, locking, `apply_defaults` on document payloads |
| `AccountsAdmin/settings_service.py` | DB-backed runtime settings (`AppSetting`) |
| `AccountsAdmin/urls.py` | routes mounted under `/api/auth/` (historical prefix — auth, users, FUB, packet preview/send, distribute) |
| `ApexIntegrationsAPI/urls.py` | everything else: deals, contracts, MLS, team, dev, defaults, portal |
| `scripts/localcheck.py` | pre-push check (system check + migration parity) with stub env |
| `static/pdfs/` | the fillable Idaho form templates (AcroForm) |
| `web/` | the React portal (see 03) — `web/dist` is served by Django |

## Data model

```
Organization (team)        CustomUser                        Deal
  id UUID                    id UUID                           id int
  name, plan_type            organization FK → team            agent FK → CustomUser (owner; never a TC)
  defaults JSON (locked)     email (login), phone, names       property_address, buyer_names, buyer_email
  is_active                  role: admin | tc | agent          listing_agent_email/name (from MLS at send)
                             is_superuser/is_staff (owner)     status: draft|out_for_signature|signed_by_buyers|fully_executed|cancelled
                             docusign_production bool          docusign_envelope_id, docusign_env (demo|production)
                             defaults JSON (own)               draft_pdf_url, signed_pdf_url, signed_re21_url (S3 keys)
                             fub_access/refresh_token,         checklist_state JSON {task_key: status}
                             fub_account_id                    form_snapshot JSON (the RE-21 as sent)
                                                               acceptance_date, is_archived, fub_synced, timestamps

DealDraft (resumable packet): id UUID, agent FK, title, source mls|dictation|manual|revision, revising_deal FK?, payload JSON {form, re14, agency, forms[], listing, source}, device ios|web

DealDocument (document trail)                 DealActivity (FUB events)            AppSetting (runtime switches)
  deal FK, doc_type re_13|re_10|re_11|other     deal FK, source 'fub', kind          key PK, value JSON, updated_by
  title, direction received|sent, sequence      title, body, actor, occurred_at
  status received|out_for_signature|signed|rejected   external_id unique "<event>:<id>"
  docusign_envelope_id, docusign_env, pdf_key, signed_pdf_key
OTPCode: user FK, code, created_at, is_used
```

Migrations `0001`–`0017` are all hand-written or generated and committed; `localcheck.py` fails if models and
migrations diverge.

## Authentication & authorization

- **Login**: email → `POST /api/auth/request-otp/` (6-digit code by email) → `POST /api/auth/verify-otp/` →
  SimpleJWT access (1 day) + refresh (60 days, no rotation). `OTP_DEV_BYPASS` lets only the owner email use `000000`.
- Every API view uses `IsAuthenticated` unless noted. Role gates: `IsAdminRole` (legacy admin endpoints),
  `team_views.IsTeamAdmin` (role admin or superuser), `dev_views.IsSuperuser`.
- **Deal visibility** is centralized in `views.deals_for(user)`: superuser → all; `tc`/`admin` → deals whose agent is
  on the same `organization`; `agent` → own. Every deal-scoped endpoint filters through it.
- **Identity on documents**: `apply_agent_identity(payload, owner)` stamps selling agent/phone/brokerage from the
  owner's DB profile; a TC sending on behalf (`agent_id` in the send body) still produces the *agent's* deal and
  identity. Then `defaults_service.apply_defaults` fills empty fields from team ⊕ agent defaults.

## Endpoints

Prefix `/api/auth/` (`AccountsAdmin/urls.py`):

| Method | Path | Notes |
|---|---|---|
| POST | `request-otp/`, `verify-otp/` | login (no auth) |
| GET | `users/me/` | current user (+ `is_superuser`, `docusign_production`, `docusign_env`) |
| GET/POST | `users/`, `organizations/`, `add-user/`, `add-organization/`, DELETE `delete-user/<uuid>/` | legacy admin endpoints (`IsAdminRole`) |
| POST | `documents/preview/<doc_type>/` | render one form → PDF bytes |
| POST | `documents/send/<doc_type>/` | **send the packet** (`re_21`): `{buyers[], re21, re14?, agencyDisclosure?, agent_id?, listing_agent_email?, listing_agent_name?, draft_id?, send_key?}` → `{status: sent|already_sent, envelope_id, deal_id}`; voids the envelope + `502 retryable` if the deal can't be saved |
| POST | `api/documents/distribute/` | email the executed RE-21 (RE-21-only copy preferred) to title/lender |
| GET/DELETE | `fub/status/`, GET `fub/connect-url/`, GET `fub/callback/`, POST `fub/backfill/`, POST `fub/send/` | FUB outbound |
| GET/POST | `fub/webhooks/` ; POST `fub/webhook/<token>/` | FUB inbound listeners (register / delivery, no auth + HMAC) |

Root (`ApexIntegrationsAPI/urls.py`):

| Method | Path | Notes |
|---|---|---|
| POST | `/api/documents/preview-bundle/` | merged packet PDF (keyed `re21/re14/agencyDisclosure`, only present keys rendered) |
| POST | `/api/contracts/webhook/` | DocuSign Connect (no auth): merges signed docs → S3, sets `fully_executed`, keeps RE-21-only copy, falls through to `DealDocument` by envelope |
| GET | `/api/contracts/status/<envelope_id>/` | envelope status via DocuSign (uses the envelope's own env) |
| GET/POST | `/api/deals/` | list (role-scoped) / create |
| GET/DELETE | `/api/deals/<id>/` | detail / delete (row first, then void envelope + S3 cleanup) |
| POST | `/api/deals/<id>/archive/` `{archived}` | |
| GET/PATCH | `/api/deals/<id>/state/` | checklist merge-by-key, `form_snapshot`, `acceptance_date` |
| POST | `/api/deals/<id>/reconcile/` | ask DocuSign: envelope + per-recipient status; **files the executed packet if completed without the webhook**; voided/declined → `cancelled` |
| POST | `/api/deals/<id>/remind/` | resend the signing email to pending signers (packet unchanged) |
| POST | `/api/deals/<id>/correct-recipient/` `{recipient_id, new_email, new_name?}` | fix a signer's email on the live envelope and resend (recipient 1 = primary buyer → `buyer_email` updated) |
| POST | `/api/deals/<id>/documents/<doc_id>/reconcile/` | same for a counter's envelope |
| GET/POST | `/api/deals/<id>/documents/` | trail / multipart upload (`file`, `doc_type`, `direction`; 25 MB) |
| POST | `/api/deals/<id>/documents/send/` | generate+send RE-13 (`fields`) **or** accept a received PDF as-is (`source_document_id`); `resulting_terms` updates `form_snapshot` |
| PATCH/DELETE | `/api/deals/<id>/documents/<doc_id>/` | status (`received|rejected|signed`) / delete |
| GET | `/api/deals/<id>/activity/` | FUB activity feed |
| GET/POST | `/api/drafts/`, GET/DELETE `/api/drafts/<uuid>/` | resumable packet drafts (own; team for TC/admin); POST upserts by client id; send with `draft_id` deletes it |
| GET | `/api/mls/search/?address=`, `/api/mls/listing/<n>/` | RESO passthrough `{value:[...]}` (address OR city; top 50) |
| GET/PATCH | `/api/defaults/` | agent's effective defaults `{team, mine, effective, locked}` / save `mine` |
| GET/PATCH | `/api/team/`, POST `/api/team/members/`, PATCH `/api/team/members/<uuid>/`, GET/PATCH `/api/team/defaults/` | team admin |
| GET/PATCH | `/api/dev/settings/`, POST `/api/dev/docusign/test/`, GET/POST `/api/dev/teams/`, PATCH `/api/dev/teams/<uuid>/`, GET/POST `/api/dev/users/`, PATCH/DELETE `/api/dev/users/<uuid>/` | superuser |
| POST | `/api/token/refresh/` | |
| GET | `/portal/…` | the web app (`web/dist/index.html`; `/portal/assets/` static) |

The Developer portal's **API Explorer** (`web/src/endpoints.ts`) is the maintained catalog of all of the above with
sample bodies — keep it in sync when adding endpoints.

## PDF pipeline

`PDFGenerationService(doc_type).generate_pdf(data)` opens the template from `static/pdfs/`, builds a field map via
`_map_re21 / _map_re14 / _map_re13 / _map_re10 / _map_re11 / _map_agency_disclosure / _map_lead_based_paint`,
fills AcroForm widgets with PyMuPDF and returns bytes. Conventions:

- JSON keys are the Swift `RE21FormData` property names (camelCase); dates ISO-8601; money numbers; enums by raw value
  (`CostPayer`: buyer/seller/shared/na, etc.).
- **Template field names are often mislabeled** (e.g. RE-14 `'3 1 BUYER'` is the date line). Mappers are verified by
  rendering marker text into fields; do the same before trusting a field name.
- DocuSign anchors are written as invisible text into the widget where the tab should land:
  `\s<n>\` sign, `\i<n>\` initial, `\d<n>\` date-signed, where n = signer index (1–2 buyers, 3–4 sellers).
- Received PDFs (counters uploaded by agents) have no anchors → `send_pdf_envelope` places tabs by **position**
  (`DocuSignService.RE13_BUYER_TABS`, from the template's widget rectangles).
- RE-14 `propertyType` accepts a list or comma string (marks every box); `searchCity/searchCounty` accept lists.

## DocuSign environments

`DocuSignService(env=None)` resolves credentials per instantiation: `env_config('demo'|'production')`.
`env_for_user(user)` = production only if master switch on ∧ `user.docusign_production` ∧ production configured.
Every envelope's environment is stored on the `Deal`/`DealDocument` and used for status, void, and download.
Never instantiate `DocuSignService()` bare in a deal context.

## Storage

`django-storages` + S3 (`default_storage`). Keys: `drafts/packet_<env>.pdf`, `signed_contracts/signed_re21_<env>.pdf`
(full packet), `signed_contracts/signed_re21_only_<env>.pdf`, `deal_documents/<deal>/…`. Serializers return
presigned URLs (5-minute expiry) — clients must not cache them.

## Envelope completion (one code path)

`views.file_completed_envelope(envelope_id, [(name, bytes)])` is the only place an envelope becomes done: merge →
S3 (`signed_re21_<env>.pdf` + RE-21-only) → `Deal` (`fully_executed`, acceptance, FUB note unless test, Pusher) or
`DealDocument` (`signed`). Callers: the Connect webhook (with `PDFBytes`, or fetching the documents itself if Connect
omitted them), `reconcile_envelope` (check-now endpoints, the app's status poll) and the management command
`python manage.py reconcile_envelopes` (schedule hourly on PythonAnywhere; `--min-age-minutes` skips envelopes the
webhook may still be delivering).

## Realtime

Pusher (`pusher_client` in views) pushes `deal-signed` style events on webhook completion; the phone also polls
`/api/deals/<id>/` every 20 s while a deal is open, and the web polls activity every 60 s.
