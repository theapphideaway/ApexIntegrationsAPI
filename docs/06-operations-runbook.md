# 06 · Operations Runbook

## Deploying the server (PythonAnywhere)

```bash
cd ~/ApexIntegrationsAPI && git pull && python manage.py migrate
```
then **Reload** the web app in the PythonAnywhere dashboard. Order matters: if a pull includes a file under
`AccountsAdmin/migrations/`, the app is broken until `migrate` runs (every request that touches the changed table
500s with "column … does not exist").

Before every push, from a dev machine:

```bash
python3 scripts/localcheck.py      # Django system check + makemigrations --check with stub env
cd web && npm run build            # if anything under web/src changed; commit web/dist
```

The web portal ships as the prebuilt `web/dist` (committed). No Node on the server.

## Environment variables (`.env` on the server)

| Group | Variables |
|---|---|
| Django | `DJANGO_SECRET_KEY`, `DATABASE_URL` (Postgres; absent → SQLite), `OTP_DEV_BYPASS` (only the owner email + code `000000`) |
| Email | `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` (Gmail SMTP; DMARC fails for business-domain recipients until SES/Postmark) |
| S3 | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME` |
| DocuSign demo | `DOCUSIGN_CLIENT_ID`, `DOCUSIGN_USER_ID`, `DOCUSIGN_ACCOUNT_ID`, file `private_key.pem` (repo root, gitignored) |
| DocuSign production | `DOCUSIGN_PROD_CLIENT_ID`, `DOCUSIGN_PROD_USER_ID`, `DOCUSIGN_PROD_ACCOUNT_ID`, file `private_key_prod.pem` (`DOCUSIGN_PROD_PRIVATE_KEY` overrides the name); optional `DOCUSIGN_PROD_BASE_PATH` (auto-resolved), `DOCUSIGN_CONNECT_HMAC_KEYS` (webhook signature check), `DOCUSIGN_WEBHOOK_URL`, `DOCUSIGN_CONSENT_REDIRECT` |
| MLS | `MLS_API_BASE_URL`, `MLS_API_TOKEN`, `MLS_LISTING_ID_FIELD` (default `ListingId`) |
| Follow Up Boss | `FUB_CLIENT_ID`, `FUB_CLIENT_SECRET`, `FUB_SYSTEM_KEY` (optional; enables HMAC verification of inbound webhooks) |
| Pusher | `PUSHER_APP_ID`, `PUSHER_KEY`, `PUSHER_SECRET`, `PUSHER_CLUSTER` |
| Identity fallbacks | `DEFAULT_SELLING_AGENT`, `DEFAULT_SELLING_BROKERAGE` |

Secrets never go in the database or the repo. Runtime *switches* live in the `AppSetting` table (Developer portal).

## Runtime settings (Developer portal → Overview)

- `docusign_env`: `demo` | `production` — the production **master switch**. Refused unless production credentials
  are fully configured. Per-user flag `CustomUser.docusign_production` selects who moves.
- Raw key/value editor for future switches. Read via `settings_service.get_setting`.

## DocuSign production cutover checklist

Everything below step 3 is driven from **Developer portal → Production cutover** (`/portal/dev`); the endpoints
are `POST /api/dev/docusign/test/`, `GET|POST /api/dev/docusign/connect/`, `GET|POST /api/dev/docusign/account-settings/`.

1. DocuSign production account (paid plan): Apps & Keys → add an integration key, generate an RSA keypair, note the
   API user's **User ID** (the impersonated sender) and the **Account ID**. Add
   `https://www.apexintegrations.ai/portal/dev` as a redirect URI on the key (the consent link returns there).
2. Server `.env`: `DOCUSIGN_PROD_CLIENT_ID`, `DOCUSIGN_PROD_USER_ID`, `DOCUSIGN_PROD_ACCOUNT_ID`; private key as
   `private_key_prod.pem` next to `manage.py`. `DOCUSIGN_PROD_BASE_PATH` is optional — the account-specific host
   (na2/na3/na4…) is resolved from userinfo and cached per process. Reload.
3. **Grant consent** (link on the Production card): sign in as the API user, Allow. Until then every call raises
   `DocuSignConsentRequired`; the dev endpoints return `{consent_required: true, consent_url}` (502).
4. **Test connection** on Production: JWT + userinfo, confirms the account id is one of the user's accounts.
5. **Signing settings → Compare / Copy demo → production**: `signDateFormat`, `signTimeFormat`, `signTimeShowAmPm`,
   `signDateTimeAccountTimezoneOverride`, `attachCompletedEnvelope` (`ACCOUNT_SETTINGS_KEYS`). The account
   **time zone** (Mountain) is not exposed on that endpoint — set it once in DocuSign Admin → Regional Settings.
6. **Connect webhook → Check production / Create webhook**: creates a `Docuflow` Connect configuration
   (envelope-completed, JSON restv2.1, documents included, HMAC on, all users, log on) pointing at
   `DOCUSIGN_WEBHOOK_URL` (default `https://www.apexintegrations.ai/api/contracts/webhook/`). Idempotent.
   If creation fails with a plan error, Connect isn't enabled on the account — ask DocuSign support.
   Then Admin → Connect → **Keys**: add an HMAC key and put it in `DOCUSIGN_CONNECT_HMAC_KEYS` (comma-separated
   for rotation). When that var is set the webhook rejects unsigned/mis-signed posts with 401; when unset it
   accepts everything (demo behaviour today — the demo config has HMAC off).
7. **Pilot**: flag one user PROD (Developer → Users), send one real packet, confirm it files as fully executed
   (webhook, or **Check now** on the deal which reconciles), then flip the master switch.
8. **Go-live** promotion of the key in Apps & Keys (self-service).
Pricing note: envelopes are per company (one API user sends everything); a deal is ~2–4 envelopes.

## Scheduled tasks (PythonAnywhere → Tasks)

| Command | Cadence | Purpose |
|---|---|---|
| `cd ~/ApexIntegrationsAPI && python manage.py reconcile_envelopes` | hourly | files envelopes that completed without the webhook; marks voided/declined |

## Follow Up Boss

- Outbound: agent connects via OAuth from the app (Profile → Integrations). Tokens on the user; refresh on 401.
  Notes are posted on packet send and on execution; `FUBBackfillView` catches up older deals.
- Inbound: webhooks are **per FUB account** (a team shares one) with a max of two per event, so they are
  registered once per account by `fub_service.ensure_webhooks(user)` (on connect, or Developer → Users →
  *listeners*, or `POST /api/auth/fub/webhooks/`). Events → `DealActivity` matched by the buyer's email.
- `FUB_SYSTEM_KEY` set → `FUB-Signature` HMAC verified; unset → the signed account token in the URL is the gate.

## Testing safely

Only the owner account can create test deals (New Deal preview → "Test deal", or mark an existing one via
`PATCH /api/dev/test-deals/`). Test deals never touch Follow Up Boss, redirect title/lender emails to the sender,
and are excluded from the owner's stats. Agents never see any of this: their deals are real. To have an agent
rehearse, do it on the owner account or mark that specific deal as test afterwards and purge it from Developer →
Test deals.

## Backups and data

- Postgres on PythonAnywhere (`apexdb`); credentials only in `DATABASE_URL`. **TODO**: scheduled `pg_dump`.
- `db.sqlite3` in the repo directory is legacy; safe to delete once Postgres has run for a while.
- S3 keys are stored on rows (`draft_pdf_url`, `signed_pdf_url`, `signed_re21_url`, `pdf_key`, `signed_pdf_key`);
  serializers mint presigned URLs (5-minute expiry) on every read.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Login 500, "column … does not exist" | pulled a migration, didn't migrate | `manage.py migrate`, reload |
| `NameError` at startup in urls.py | view not imported | run `scripts/localcheck.py` before pushing |
| Webhook 400 "Missing PDFBytes" | Connect config without *Include Document PDFs* | the webhook now fetches the documents itself; still fix Connect config |
| Deal stuck "Awaiting signature" though buyers signed | webhook never delivered | Check now on the deal, or wait for the hourly `reconcile_envelopes` |
| Phone checklist ≠ web checklist | old build / failed push | app reconciles on next open; server wins per key |
| No deadlines on a deal | executed before `form_snapshot`/`acceptance_date` existed | resend, or accept the gap |
| OTP emails not arriving at a business domain | Gmail SMTP + DMARC | SES/Postmark with domain auth (planned) |
| DocuSign tab in the wrong place | template field names are mislabeled | see `pdf_service.py` comments; verify by rendering markers |
| Slow / hung server, `database is locked` | SQLite (pre-Postgres) or stuck console holding locks | close consoles, reload; ensure `DATABASE_URL` is set |

## Known landmines (fix before wide rollout)

- OpenAI API key is embedded in the iOS app (`AppFactory`) — move dictation extraction behind the server.
- Secrets that were once in git history should be rotated (DocuSign key, AWS, Pusher).
- The `000000` OTP bypass exists for the owner account only (`OTP_DEV_BYPASS`); testers must use real codes.
- `DealSerializer.get_agent_id` falls back to a hard-coded admin id when a deal has no agent (legacy data only).
