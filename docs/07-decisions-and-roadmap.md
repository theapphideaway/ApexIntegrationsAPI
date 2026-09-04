# 07 · Decisions & Roadmap

## Decisions (with the why)

| Decision | Why |
|---|---|
| **Postgres, not MySQL/SQLite** | SQLite locked the whole API twice under concurrent webhooks + consoles; MySQL was explicitly rejected. Postgres add-on on PythonAnywhere via `DATABASE_URL`. |
| **Agent teams, not brokerages** | The customer is a team lead; `Organization` = team; one team per person; admin may also be a working agent. |
| **Deal owner is always the agent** | A TC sending on behalf still creates the agent's deal, identity, and CRM entry. |
| **Server is the source of truth for checklist state** | Phone and web both edit; merge per key; phone only fills gaps. |
| **Web portal inside the Django repo, served at `/portal/`** | One domain, one deploy, no CORS, no Node on the server (built `dist` committed). |
| **Per-user DocuSign environment + master switch** | Lets production be set up ahead of time and flipped once; envelopes remember their account. |
| **Accept & Sign sends the received PDF as-is** | Agents don't want to retype the seller's counter; positional tabs on the standard RE-13 layout. |
| **Forwarding buyer counters to the listing agent by email** | The MLS has no seller contact; listing agents collect their seller's signature on their own system. |
| **Team defaults lock the *default*, not the per-deal value** | A negotiated per-deal term must never be silently overwritten at send. |
| **Local notifications, not APNs (for now)** | Deadlines are computed on-device from the contract; no push infrastructure needed. |
| **No test-looking features for agents** | Agents are on real deals from day one; test deals exist only for the owner (server-enforced flag visibility), no toggles anywhere in the app. |
| **New Deal on the web is agent-only** | Explicit product decision; superuser exempt for testing. |
| **MLS is always live** | The mock toggle was removed; the credential lives only on the server. |
| **Superuser sees everything** | Owner account is auto-promoted by migration `0012`; `deals_for` returns all deals. |

## Roadmap (agreed order)

1. **DocuSign production** (blocked on business-partner approval of the plan; runbook in 06).
2. **Brokerage-specific signable document onboarding** — decision pending: admin self-serve field mapping
   (upload PDF → detect fields → map to data + signature spots) vs. done-for-them per brokerage.
3. Seller-side signing via DocuSign (role-based recipients; seller anchors already in templates).
4. Email deliverability: SES/Postmark with domain authentication (Gmail SMTP fails DMARC for business domains).
5. Move the OpenAI key behind the server; rotate history-exposed secrets; scheduled `pg_dump`.
6. Email-in ("a deal has an email address"): inbound parse → classify attachments → prefill counters, auto-complete tasks.
7. Mobile navigation for the web portal (sidebar hides < 900 px).
8. Agents' saved defaults overlay on the web review (done via server-side fill; UI parity optional).

## Open questions

- Should locked team defaults also be immovable on every packet (currently per-deal edits win)?
- FUB: confirm OAuth tokens may create webhooks for the Top Notch account (else system-key registration).
