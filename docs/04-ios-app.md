# 04 · iOS App (SwiftUI)

Repo: `RealEstateAI/` (Xcode project `RealEstateAI.xcodeproj`, scheme `RealEstateAI`, bundle
`com.ianschoenrock.RealEstateAI`, marketing version 1.0.x). iOS 17+, SwiftUI, Swift Package deps: `pusher-websocket-swift`,
`twilio-voice-ios`. File-system-synchronized groups: adding a file under `RealEstateAI/` adds it to the target.

Build / test from the command line:

```bash
xcodebuild -project RealEstateAI.xcodeproj -scheme RealEstateAI -destination 'generic/platform=iOS Simulator' build CODE_SIGNING_ALLOWED=NO
xcodebuild -project RealEstateAI.xcodeproj -scheme RealEstateAI -destination 'platform=iOS Simulator,id=<udid>' test CODE_SIGNING_ALLOWED=NO
```
Tests live in `RealEstateAITests/` (validation view model, MLS timeline, collapsible section).

## Architecture

- **Entry**: `RealEstateAIApp` → `ContentView` (tabs: Pipeline, Archive, Profile) gated by `AuthManager.shared.isAuthenticated`.
- **Coordinator**: `FormFlowCoordinator` (`@MainActor ObservableObject`) owns a `NavigationPath` of `FormRoute`
  (`recording, dialer, manualValidation, validation, pdfReview, mlsLookup, dealDashboard(Deal)`), the in-flight form
  state (`capturedFormData: RE21FormData`, `packetRE14`, `packetAgency`, `selectedBundleForms`), the active deals
  list, Pusher, and the send/preview pipeline. ViewModels for the review screens are cached per flow because
  `navigationDestination` closures re-run on every publish.
- **Services** (`Services/`): `AuthManager` (JWT in Keychain, refresh, `performAuthenticatedRequest`), `DealService`
  (deals, state, documents, activity, counters), `PDFGenerationService` (preview/send bodies), `MLSService`
  (`LiveMLSService` → server proxy; mock exists for tests only — production is always live), `OpenAIExtractionService`
  (dictation → RE-21; key embedded — landmine), `TranscriptionService`, `AudioRecordingService`, `FUBOAuthService`,
  `ContractDefaultsService`, `DeadlineNotifications`, `ProfileManager` (profile + defaults), `EmailService`,
  `VoiceCallingService` (Twilio), `PersistenceService`.
- **Factory**: `AppFactory.shared` builds services/coordinators (single place to swap implementations).
- **Config**: `AppConfig` — `apiBaseURL`, `s3Host` (+ `s3URL(forKey:)`), `voiceBaseURL`.

## Models (`Models/`)

- `RE21FormData` — the whole RE-21 (Codable; JSON keys = property names = server keys). Extensions:
  `fillingEmptyFields(from:)` (JSON overlay; non-nil wins), `applyingLoanTypePresets()`.
- `RE14Payload`, `AgencyDisclosurePayload`, `RE10Payload`, `RE11Payload`, `SignerPayload`, `PacketPayloadBuilder`
  (`DocumentType.swift`) — builds `{buyers, re21, re14, agencyDisclosure, listing_agent_*}` with only selected forms.
- `Deal` (server row incl. `signedRe21Url`, `listingAgentEmail`, `docusignEnvelopeId`), `DealDocumentItem`,
  `DealActivityItem`, `MLSListing` (+ `RESORecord.toListing()` and `prefill(into:)`), `TransactionTimeline`
  (deadline engine; mirrored in web `deadlines.ts`), `SectionIdentifier` (10 review sections + required fields),
  `FormField`/`ValidationResult`, enums `CostPayer`, `AgencyType`, `FinancingType`, `YesNoNA`…
- `MockData.swift` holds the **TC checklist template** (`TCChecklistViewModel`, `TCPhase`, `TCTask`, email templates,
  `EmailRecipientRole`). Task keys `p1.1…p4.5` must match `web/src/checklist.ts`.
- Local stores (UserDefaults): `DealTimelineStore` (form snapshot + acceptance per deal), `DealContactsStore`
  (listing agent email per deal), checklist status cache + dirty flag, contract defaults caches.

## Screens (`Views/`)

| Screen | Role |
|---|---|
| `LoginView` | OTP login |
| `HomeDashboardView` / `DealsPipelineView` | active deals (30 s refresh), `DealCard` with packet chip, long-press Archive / View packet |
| `ArchiveView` | archived deals, restore / delete |
| `RecordingView`, `DialerView` | dictation & call capture → OpenAI extraction → review |
| `MLSLookupView` | address/city/MLS# search with photo cards → prefilled review |
| `ValidationView` (+ `PacketFormTabs`, `Components/*Row`) | the review form: RE-21 / RE-14 / Agency tabs, form pills, section validation, "Almost there" |
| `PDFPreviewView` (+ `QuickEditSheet`) | merged packet preview, quick edits, Send for Signatures |
| `DealCommandCenterView` | deal dashboard: counter banner, deadlines, 4-phase checklist (`TaskRow` with per-step document buttons, Edit & Resend), Current Documents (+Add / counter sheet), FUB activity card, mailto drafts, live signed sync (Pusher + 20 s poll), server state reconcile |
| `CounterOfferSheet` | View / Accept & Sign (as-is) / Counter Back / Mark Rejected |
| `ProfileView` → `TemplateEditorView`, `ContactDefaultsView` | agent defaults (team-locked rows disabled), closing contacts & fees, FUB connect |
| `DeveloperSettingsView` | debug-only |

## Sync rules (important)

- **Checklist**: local cache + push on every change; on open, `syncWithServer`: server wins per key, local
  non-empty statuses the server lacks are pushed, a failed push sets a dirty flag and re-sends next open.
- **Form snapshot / acceptance**: pulled from `/state/` if missing locally so timelines and Edit & Resend work on
  any device.
- **Defaults**: team layer + locked keys cached; agent edits push `mine`; effective = team over agent; forms start
  from `ProfileManager.effectiveFormData` and `freshRE14()`.
- **Deadlines**: computed on device from the snapshot; local notifications day-before 9:00 and day-of 8:00;
  cancelled on archive/delete.
- **Drafts**: `beginDraft` at every packet entry point; Combine observers on the review VM autosave; `resumeDraft` rebuilds the flow from the payload; send passes `draft_id` and the server deletes it.
- **Deletion**: `pendingDeletionIds` hides a deal immediately and filters it out of refreshes until the server confirms.

## Release notes

The team installs TestFlight builds. Server-only changes need no release; anything under `RealEstateAI/` does.
Commit the iOS repo regularly — the working tree has carried large uncommitted change sets.
