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
| DocuSign production | `DOCUSIGN_PROD_CLIENT_ID`, `DOCUSIGN_PROD_USER_ID`, `DOCUSIGN_PROD_ACCOUNT_ID`, `DOCUSIGN_PROD_BASE_PATH` (e.g. `https://na4.docusign.net/restapi`), file `private_key_prod.pem` (`DOCUSIGN_PROD_PRIVATE_KEY` overrides the name) |
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

1. Production account: create integration key, RSA keypair, note API user ID, account ID, base URI.
2. Grant consent for the key (one-time, as the impersonated user).
3. Put the four `DOCUSIGN_PROD_*` vars + `private_key_prod.pem` on the server; reload.
4. Developer portal → DocuSign environments → **Test connection** on Production (JWT + userinfo; checks the account id).
5. Account settings on production (as on demo): signing time format `h:mm` + AM/PM, timezone Mountain
   (`TZ_55_MountainStandardTime`), `signDateTimeAccountTimezoneOverride`, `attachCompletedEnvelope`.
6. Connect webhook on production → `https://www.apexintegrations.ai/api/contracts/webhook/`, event
   *envelope-completed*, **Include Document PDFs** on (the webhook needs `PDFBytes`).
7. Flag one user PROD (Developer → Users), send one real packet, verify the webhook filed it, then flip the master.
8. Go-live promotion of the key in DocuSign Apps & Keys (self-service now; no 20-call rule).
Pricing note: envelopes are per company (one API user sends everything); a deal is ~2–4 envelopes.

## Follow Up Boss

- Outbound: agent connects via OAuth from the app (Profile → Integrations). Tokens on the user; refresh on 401.
  Notes are posted on packet send and on execution; `FUBBackfillView` catches up older deals.
- Inbound: webhooks are **per FUB account** (a team shares one) with a max of two per event, so they are
  registered once per account by `fub_service.ensure_webhooks(user)` (on connect, or Developer → Users →
  *listeners*, or `POST /api/auth/fub/webhooks/`). Events → `DealActivity` matched by the buyer's email.
- `FUB_SYSTEM_KEY` set → `FUB-Signature` HMAC verified; unset → the signed account token in the URL is the gate.

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
| Webhook 400 "Missing PDFBytes" | Connect config without *Include Document PDFs* | fix Connect config |
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
