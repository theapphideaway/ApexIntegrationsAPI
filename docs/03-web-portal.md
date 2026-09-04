# 03 · Web Portal — "Docuflow Dashboard"

Location: `ApexIntegrationsAPI/web/`. React 18 + TypeScript + Vite + react-router. No UI framework; a hand-written
design system in `src/styles.css`. Served by Django at **https://www.apexintegrations.ai/portal/** from the
committed build in `web/dist` (same origin as the API → no CORS, no separate hosting).

## Build & run

```bash
cd web && npm install
npm run dev        # http://localhost:5173/portal/ — proxies /api to production (vite.config.ts)
npm run build      # → web/dist (commit it; that is the deploy artifact)
```
`vite.config.ts` sets `base: '/portal/'`. Django routes `^portal/assets/` to `web/dist/assets` and `^portal(?:/.*)?$`
to `index.html` (`views.portal_index`), so client-side routing works on refresh.

## Source map

| File | Purpose |
|---|---|
| `src/main.tsx` | mounts the app with `BrowserRouter basename="/portal"`; `initTheme()` before first paint |
| `src/App.tsx` | shell: sidebar nav (role-gated), top bar, routes, theme toggle, console toggle; exports `ROLE_LABEL`, `initials` |
| `src/api.ts` | typed API client: JWT in `localStorage` (`portal_access/refresh`), silent refresh on 401, `consoleBus` (every call is published for the dev console), `authFetch` (raw), `requestBlob` (PDF) |
| `src/theme.ts` | light/dark: `localStorage docuflow_theme`, OS default, `data-theme` on `<html>` |
| `src/styles.css` | tokens (`--bg --surface --ink --accent --ok/--warn/--bad …`), dark overrides under `:root[data-theme="dark"]`, all component classes |
| `src/checklist.ts` | the 4-phase TC checklist template — **task keys must match iOS** (`p1.1 … p4.5`) |
| `src/deadlines.ts` | port of the iOS `TransactionTimeline` engine (same rules) + `urgency()` |
| `src/mls.ts` | RESO record → `Listing` (port of `MLSListing.swift`) |
| `src/re21.ts` | RE-21 form model: `defaultRE21()`, `prefillFromListing`, `applyLoanTypePresets`, `applyDefaults`, `SECTIONS` schema (same 10 sections / labels / required as the iOS review screen), RE-14/Agency fields, `buildPacket` (= iOS `PacketPayloadBuilder`), `DEFAULT_SECTIONS`, `CONTACT_FIELDS`, `FEE_FIELDS`, `NEVER_DEFAULT` |
| `src/endpoints.ts` | API Explorer catalog — every endpoint with prefilled params/body/danger flags |
| `src/pages/Login.tsx` | OTP login (split brand panel) |
| `src/pages/Pipeline.tsx` | stat tiles + deal rows grouped by agent (TC/admin) or "All Deals" (superuser); archive/restore |
| `src/pages/DueSoon.tsx` | agenda of computed deadlines across visible deals; agent + horizon filters |
| `src/pages/Deal.tsx` | hero header, counter banner, deadlines, checklist (checkbox + status select, per-step document links), documents + drag-and-drop upload, FUB activity feed |
| `src/components/CounterForm.tsx` | Accept received counter as-is (one click, optional resulting terms) or send a buyer counter (RE-13 form) |
| `src/pages/NewDeal.tsx` | agent-only "Start from property": MLS search → review (RE-21/RE-14/Agency tabs, form pills, validation, locked team defaults) → PDF preview → send; exports `FieldGrid`/`FieldInput` |
| `src/pages/Team.tsx` | team admin: members/roles/invites, **team defaults** editor |
| `src/pages/Dev.tsx` + `ApiExplorer.tsx` | superuser: DocuSign environments + master switch, per-user PROD/TEST, teams, users, raw settings, API explorer |
| `src/components/Console.tsx` | right-hand drawer logging all API traffic (superuser) |

## Roles in the UI

| Route | Who |
|---|---|
| `/` Pipeline, `/due`, `/deals/:id` | everyone (server scopes the data) |
| `/new` | `agent`, and superuser |
| `/team` | `admin`, and superuser |
| `/dev`, `/dev/api` | superuser only |

`me.is_superuser` also unlocks "All Deals" grouping by agent · team and the console.

## Conventions

- All colors through tokens; never hard-code hex in components (dark mode depends on it).
- New server endpoint ⇒ add to `endpoints.ts` and `api.ts`.
- Checklist keys, deadline rules, RE-21 field keys and validation must stay identical to iOS; change both.
- Optimistic updates for checklist; the server merges per key, so concurrent phone/web edits don't clobber.
- Presigned S3 URLs expire in 5 minutes — always re-fetch the deal/documents before opening a link after idling.
