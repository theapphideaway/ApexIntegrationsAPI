# Docuflow — Documentation Index

Docuflow (product name; repo names are historical) is a buyer-side **transaction coordination platform** for
Idaho real-estate agent teams: MLS listing → prefilled Idaho forms (RE-21 / RE-14 / Agency Disclosure) →
DocuSign signatures → deal dashboard with a shared checklist, deadlines, documents and counter offers → CRM
(Follow Up Boss) in both directions.

Three codebases, one backend:

| Piece | Where | Doc |
|---|---|---|
| Django REST API + workers (system of record) | `ApexIntegrationsAPI/` (this repo) | [02-server-architecture.md](02-server-architecture.md) |
| Web portal "Docuflow Dashboard" (React SPA, served by Django at `/portal/`) | `ApexIntegrationsAPI/web/` | [03-web-portal.md](03-web-portal.md) |
| iOS app (SwiftUI) | `RealEstateAI/` (separate repo) | [04-ios-app.md](04-ios-app.md) |

Read in this order:

1. [01-system-overview.md](01-system-overview.md) — what it does, who the users are, how the pieces talk, environments.
2. [05-features.md](05-features.md) — every feature: what it does, where the code is, the endpoints, the edge cases.
3. The platform doc for whatever you are changing (02 / 03 / 04).
4. [06-operations-runbook.md](06-operations-runbook.md) — deploying, migrations, env vars, DocuSign/FUB setup, troubleshooting.
5. [07-decisions-and-roadmap.md](07-decisions-and-roadmap.md) — why things are the way they are, and what's next.

For an AI agent picking this up: also read `AGENTS.md` at each repo root (conventions and non-negotiables).
