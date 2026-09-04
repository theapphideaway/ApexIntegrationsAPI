# 01 · System Overview

## What the product does

An agent (or their transaction coordinator, "TC") starts a deal from a **live MLS listing**. The app prefills the
Idaho purchase packet — **RE-21** Purchase & Sale Agreement, **RE-14** Buyer Representation Agreement, and the
**Agency Disclosure Brochure** — from the listing, the agent's/team's saved defaults, and (on the phone) optional
dictation. The agent reviews, previews the merged PDF, and sends it to the buyer(s) through **DocuSign**.

When the envelope completes, a DocuSign **Connect webhook** stores the executed packet (plus an RE-21-only copy for
title/lender), marks the deal *fully executed*, records the acceptance date, and posts the packet to the buyer's
**Follow Up Boss** timeline. The **deal dashboard** (phone + web) then drives the transaction: a 4-phase TC
checklist synced across devices, contract deadlines computed from the executed terms (with on-device reminders),
the document trail (counters, RE-10s, uploads), counter-offer handling, and a feed of what happened in FUB.

## Users and roles

| Role | Sees | Can |
|---|---|---|
| `agent` | own deals | create deals (MLS / dictation / manual on phone; MLS on web), work checklist, send counters |
| `tc` (Transaction Coordinator) | every deal on their team | everything an agent can on any team deal, send packets on an agent's behalf |
| `admin` (Team Admin / team lead) | team deals | TC powers + manage team members/roles + **team contract defaults** (web) |
| superuser (platform owner) | everything | Developer portal: runtime settings, DocuSign env per user, teams/users, API explorer |

Business model: **agent teams** (an `Organization` is a team), not brokerages. One team per person.
Every deal belongs to exactly one agent (`Deal.agent`); TC/admin visibility is derived from the agent's team.

## Topology

```
iPhone app (SwiftUI)  ─┐                       ┌─ MLS (RESO Web API via rets.io; credential server-side only)
                       ├─ HTTPS/JSON (JWT) ──► Django REST API ─┼─ DocuSign eSignature (JWT grant; demo + production accounts)
Web portal (React) ────┘   www.apexintegrations.ai              ├─ Follow Up Boss (OAuth; notes out, webhooks in)
   served by Django at /portal/                                  ├─ OpenAI (dictation → RE-21 extraction; key in app — see landmines)
                                                                 ├─ AWS S3 (PDFs; presigned URLs, 5-min expiry)
                                                                 ├─ Pusher (live "signed" push to the phone)
                                                                 ├─ Gmail SMTP (OTP + invites; DMARC caveat)
                                                                 └─ Postgres (PythonAnywhere add-on)
Inbound webhooks: DocuSign Connect (/api/contracts/webhook/), FUB (/api/auth/fub/webhook/<token>/)
```

Hosting: **PythonAnywhere** (`ianschoenrockpersonal`), deployed by `git pull` + `manage.py migrate` + web-app reload.
The web portal is a prebuilt bundle committed in `web/dist`, so the server never needs Node.

## Core data flow (a deal's life)

1. **Create**: `POST /api/auth/documents/send/re_21/` with `{buyers, re21, re14?, agencyDisclosure?, listing_agent_*}` →
   PDFs generated from the templates in `static/pdfs/` → one DocuSign envelope → `Deal` row (`out_for_signature`),
   draft packet in S3, `form_snapshot` = the RE-21 as sent, FUB note.
2. **Sign**: DocuSign emails the buyers. Anchor strings stamped invisibly in the PDFs place signature / initial /
   date tabs.
3. **Complete**: Connect webhook (`envelope-completed`, with PDF bytes) → merged executed packet + RE-21-only copy
   → `status=fully_executed`, `acceptance_date`, FUB note, Pusher push. Counter-offer envelopes hit the same
   webhook and are matched to `DealDocument` rows instead.
4. **Work the deal**: checklist state (`Deal.checklist_state`) merged per task key from any client; deadlines are
   computed client-side from `acceptance_date` + `form_snapshot` day counts (identical engine in Swift and TS);
   documents added by upload (phone/web) or generated (RE-13); FUB activity matched to the deal by buyer email.
5. **Close/archive/delete**: archive hides; delete voids an in-flight envelope and removes files.

## Environments

- **DocuSign**: demo (sandbox) by default. Production is per-user: a user's envelopes go to production only if the
  *production master switch* (runtime setting) is on AND the user is flagged AND production credentials exist.
  Every envelope records which account it lives in (`docusign_env`).
- **Database**: Postgres in production (`DATABASE_URL`); SQLite only as a local fallback.
- **Local dev**: `python3 scripts/localcheck.py` runs Django's system check with stub env vars; the web portal can
  run on Vite (`web/`, proxies `/api` to production).
