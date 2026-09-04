# 05 · Features — what, where, how

Each feature: what it does, where the code lives (server / web / iOS), the endpoints, and the edge cases.

## 1. Start a deal from the MLS
- **What**: search by address, city, or MLS number; photo cards; picking a listing prefills the RE-21 (address, city,
  state, zip, county, parcel, legal description, list price as starting offer, pre-1978 lead-paint flag, HOA dues +
  frequency) and captures the listing agent's email/name for later.
- **Server**: `MLSAddressSearchView` (`address` matches `UnparsedAddress` OR `City`, top 50), `MLSListingProxyView`
  (`ListingId eq`), `mls_reso_query` against `MLS_API_BASE_URL` with the server-held token. RESO envelope passthrough.
- **iOS**: `MLSLookupView`, `LiveMLSService`, `MLSListing.prefill(into:)`, `FormFlowCoordinator.startFromListing` +
  `enrichWithMLS` (dictation flows also try to match the extracted address to a listing).
- **Web**: `NewDeal.tsx` (agent-only), `mls.ts`, `re21.ts` prefill.
- **Edge**: MLS feed is IDX Active only; no seller name/contact in the feed; mock MLS exists only for unit tests.

## 2. Packet review, preview, send (RE-21 / RE-14 / Agency)
- **What**: three tabs, form pills to include/exclude forms, 10 RE-21 sections with required-field validation
  (address, buyer name/email/phone, seller name, offer price, closing date), loan-type presets (cash → lender fees
  N/A; VA → doc prep/tax service/attorney to seller), RE-14 multi-select property type + multiple cities/counties,
  agency election (RE-14 page 3 initials), quick edits from the PDF screen.
- **Server**: `OnboardingBundlePreviewEndpoint` (merged PDF), `SendOnboardingBundleEndpoint` (envelope + `Deal` +
  draft to S3 + `form_snapshot` + FUB note; TC send-on-behalf via `agent_id`). `apply_agent_identity` then
  `defaults_service.apply_defaults` on every document payload.
- **iOS**: `ValidationView`, `PacketFormTabs`, `PDFPreviewView`, `QuickEditSheet`, `PacketPayloadBuilder`.
- **Web**: `NewDeal.tsx` (stepper: find → review → preview & send).
- **Edge**: single buyer must not print "and"; agency brochure has only signature/date fields; RE-14 template field
  names are mislabeled (mapped by rendered position).

## 3. DocuSign signing & completion
- **What**: one envelope per packet, remote signing by email, signature/initial/date tabs placed by anchor strings;
  completion webhook files the executed packet, an RE-21-only copy, sets `fully_executed` + `acceptance_date`,
  FUB note, Pusher push; phone updates within a minute (push + poll) and auto-checks checklist steps 1–2.
- **Server**: `docusign_service.py`, `docusign_webhook`, `RE21ContractStatusEndpoint`, `DistributeExecutedPacketEndpoint`.
- **Env**: demo/production per user (`env_for_user`), master switch, `docusign_env` recorded per envelope.
- **Edge**: Connect must send PDF bytes; certificate doc skipped; DateSigned tabs need the account time settings for
  time stamps; voided envelopes still count toward the plan.

## 4. Deal dashboard & TC checklist
- **What**: 4 phases × 19 tasks (`p1.1…p4.5`), statuses Not Started / In Progress / Waiting / Complete / N/A,
  checkbox toggle, email-draft actions (mailto with executed-packet or RE-21-only link, recipients from defaults),
  file-attachment tasks via share sheet, Edit & Resend (void + new envelope, old deal deleted), per-step
  "View Packet"/"View RE-10" buttons.
- **Server**: `DealStateView` (merge by key), `DealArchiveView`, `DealDetailEndpoint.perform_destroy`.
- **iOS**: `DealCommandCenterView`, `TaskRow`, `TCChecklistViewModel` (sync rules in 04).
- **Web**: `Deal.tsx` checklist with per-phase progress bars, `Pipeline.tsx`, `DueSoon.tsx`.

## 5. Deadlines & reminders
- **What**: from acceptance date + contract day counts: earnest money, title commitment/objection, inspection +
  seller response, appraisal day 13/18 targets, offer expiration, closing. Shown on the dashboard, pipeline row
  (next deadline), Due Soon board; on-device reminders day-before and day-of.
- **Code**: `TransactionTimeline.swift` ≡ `web/src/deadlines.ts`; `DeadlineNotifications.swift`.
- **Edge**: deals executed before `form_snapshot` existed have no timeline (fall back only for acceptance date).

## 6. Documents trail
- **What**: per-deal documents beyond the packet — received counters (uploaded from phone Files or dragged onto
  the web deal), sent counters, RE-10s, other uploads — with viewer, status, forward-to-listing-agent.
- **Server**: `DealDocument` + `DealDocumentsView` (multipart), `DealDocumentDetailView` (PATCH status / DELETE).
- **Storage**: `deal_documents/<deal>/…`; presigned links.

## 7. Counter offers (RE-13)
- **Receive**: upload as "Counter Offer (received)" → orange banner (phone + web), auto-numbered.
- **Accept & Sign**: sends the *received PDF untouched* to the buyer with positional tabs (`send_pdf_envelope`,
  `RE13_BUYER_TABS`); optional "resulting terms" (price/closing) update `form_snapshot` → deadlines recompute.
- **Counter Back / new counter**: typed RE-13 generated server-side (`_map_re13`), buyer-originated; after the buyer
  signs, "Send to listing agent" opens a mailto with the signed PDF link (listing agent captured at send).
- **Mark Rejected**: `PATCH …/documents/<id>/ {status: rejected}`.
- **Server**: `DealDocumentSendView` (both modes), webhook fall-through by envelope id.
- **iOS**: `CounterOfferSheet`; **Web**: `CounterForm.tsx`.
- **Not yet**: seller signing through our DocuSign (needs seller email; role-based recipients designed, anchors
  `\s3\ \s4\` already in templates).

## 8. Follow Up Boss (CRM)
- **Outbound**: OAuth connect (signed `state`), person find/create by buyer email, notes on send + completion,
  backfill. Never blocks the deal flow.
- **Inbound**: account-level webhooks (notes/tasks/appointments/calls/texts/emails/deals/stage), resource fetched
  with any connected user's token, matched to deals by buyer email within the account's teams → `DealActivity`;
  shown on the web deal page and the phone dashboard. Register once per account (Developer → Users → listeners).
- **Code**: `fub_service.py`, `FUB*View`s, `FUBOAuthService.swift`, `DealActivityItem.swift`.

## 9. Contract defaults (team-locked + agent)
- **What**: team lead sets team defaults on the web (contacts, RE-14 fees, RE-21 terms); every key set is locked
  for agents; agents set the rest (app: Default Contract Terms + Closing Contacts & Fees). Forms start from
  effective defaults (team ⊕ agent), then MLS, then presets, then typing. Server fills any blank field at
  preview/send. Per-deal edits are never overwritten.
- **Code**: `defaults_service.py`, `ContractDefaultsView`/`TeamDefaultsView`, `re21.ts` (`applyDefaults`,
  `DEFAULT_SECTIONS`), `Team.tsx`, `ProfileManager.swift`, `ContractDefaultsService.swift`, `ContactDefaultsView.swift`.

## 10. Teams, roles, portals
- **Team admin** (web `/team`): members, roles, invites (email), deactivate, team defaults.
- **TC** (web): team pipeline grouped by agent, Due Soon, deal pages, drag-and-drop docs, counters.
- **Developer** (web `/dev`, superuser): DocuSign environments + master switch + per-user PROD/TEST + connection
  test, teams, users (role/team/active/delete, FUB listeners), raw runtime settings, API Explorer, console.
- **Visibility**: `deals_for(user)`; superuser bootstrap migration `0012` promotes the owner account.

## 11. Executed RE-21-only distribution
- Webhook keeps the signed RE-21 alone (`signed_re21_url`); the distribute endpoint and the phone's title/escrow/
  lender email drafts use it; buyer emails get the full packet. Older deals fall back to the full packet.

## 12. Archive / delete
- Archive (context menu / row action) hides from the pipeline; Archive tab restores. Delete removes the row first,
  then voids the envelope and cleans S3; phone hides it immediately and ignores it in refreshes until confirmed.

## 13. Drafts (off-ramp: never lose a half-built packet)
- **What**: every packet flow (MLS, dictation, manual, revision) saves a server-side draft as the agent types
  (debounced ~1.5 s); a **Drafts** strip on the pipeline (phone + web) resumes it on any device; sending deletes it;
  discard/delete available. TCs/admins see their team's drafts and can finish one.
- **Server**: `DealDraft`, `DealDraftsView` (upsert by client-generated UUID → idempotent), `drafts_for`.
- **iOS**: `DraftService`, `FormFlowCoordinator.beginDraft/scheduleDraftSave/resumeDraft`, `DealsPipelineView.draftsSection`.
- **Web**: `NewDeal.tsx` autosave + `?draft=<id>` resume, `Pipeline.tsx` Drafts strip.
- **Payload contract** (shared): `{form: RE-21 JSON with ISO dates, re14, agency, forms: ["re_21","re_14","agency_disclosure"], listing, source}`.

## 14. Atomic send (off-ramp: never a packet we don't know about)
- **What**: every send carries a `send_key` (the draft id, or a per-attempt UUID). A retry with the same key returns
  the existing deal/document (`status: already_sent`) instead of creating a second envelope. If the envelope was
  created but the `Deal`/`DealDocument` row can't be saved, the server **voids the envelope**, deletes the draft PDF,
  and answers `502 {error, retryable: true}` with plain language ("The packet was NOT sent…"). Concurrent duplicate
  sends collide on the unique key; the loser voids its envelope and returns the winner.
- **Code**: `SendOnboardingBundleEndpoint`, `DealDocumentSendView`; iOS `FormFlowCoordinator.sendKey`,
  `CounterOfferSheet.sendKey`; web `buildPacket` (`send_key = draftId`), `CounterForm`.

## 15. Dictation → RE-21 (phone only)
- Record → transcription → OpenAI structured extraction → RE-21 → MLS enrichment by extracted address → review.
  The OpenAI key is in the app; move it behind the server before wide release.
