// Every endpoint the server exposes, for the Developer portal's API explorer.
// Path params are written as :name and filled from `params`. Bodies are
// editable JSON. `danger` = has real side effects (sends envelopes, deletes).
export type Endpoint = {
  id: string; group: string; method: 'GET' | 'POST' | 'PATCH' | 'DELETE'; path: string; title: string; note?: string
  params?: Record<string, string>; query?: Record<string, string>; body?: unknown; danger?: string; binary?: boolean; noAuth?: boolean
}

export type Prefill = { dealId: string; docId: string; envelopeId: string; userId: string; otherUserId: string; teamId: string; email: string; address: string; fubToken: string }

export function catalog(pf: Prefill): Endpoint[] {
  return [
    // ---- Auth ----
    { id: 'otp-request', group: 'Auth', method: 'POST', path: '/api/auth/request-otp/', title: 'Request login code', noAuth: true, body: { email: pf.email }, note: 'Emails a 6-digit code (the owner account gets the bypass).' },
    { id: 'otp-verify', group: 'Auth', method: 'POST', path: '/api/auth/verify-otp/', title: 'Verify code → tokens', noAuth: true, body: { email: pf.email, code: '000000' } },
    { id: 'token-refresh', group: 'Auth', method: 'POST', path: '/api/token/refresh/', title: 'Refresh access token', noAuth: true, body: { refresh: '<paste refresh token>' } },
    { id: 'me', group: 'Auth', method: 'GET', path: '/api/auth/users/me/', title: 'Current user' },
    { id: 'users', group: 'Auth', method: 'GET', path: '/api/auth/users/', title: 'List users (admin)' },
    { id: 'orgs', group: 'Auth', method: 'GET', path: '/api/auth/organizations/', title: 'List organizations (admin)' },
    { id: 'add-org', group: 'Auth', method: 'POST', path: '/api/auth/add-organization/', title: 'Add organization (admin)', body: { name: 'Test Team', plan_type: 'basic' }, danger: 'Creates a team.' },
    { id: 'add-user', group: 'Auth', method: 'POST', path: '/api/auth/add-user/', title: 'Add user + invite email (admin)', body: { email: 'new.agent@example.com', first_name: 'New', last_name: 'Agent', phone_number: '', role: 'agent', organization: pf.teamId }, danger: 'Creates a user and emails them.' },
    { id: 'del-user', group: 'Auth', method: 'DELETE', path: '/api/auth/delete-user/:user_id/', title: 'Delete user (admin)', params: { user_id: pf.otherUserId }, danger: 'Permanently deletes that user.' },

    // ---- Deals ----
    { id: 'deals', group: 'Deals', method: 'GET', path: '/api/deals/', title: 'List deals (role-scoped)' },
    { id: 'deal', group: 'Deals', method: 'GET', path: '/api/deals/:id/', title: 'Deal detail', params: { id: pf.dealId } },
    { id: 'deal-archive', group: 'Deals', method: 'POST', path: '/api/deals/:id/archive/', title: 'Archive / restore', params: { id: pf.dealId }, body: { archived: true } },
    { id: 'deal-delete', group: 'Deals', method: 'DELETE', path: '/api/deals/:id/', title: 'Delete deal (voids envelope)', params: { id: pf.dealId }, danger: 'Deletes the deal, voids its DocuSign envelope, removes its files.' },
    { id: 'state-get', group: 'Deals', method: 'GET', path: '/api/deals/:id/state/', title: 'Deal state (checklist, snapshot, acceptance)', params: { id: pf.dealId } },
    { id: 'state-patch', group: 'Deals', method: 'PATCH', path: '/api/deals/:id/state/', title: 'Merge checklist statuses', params: { id: pf.dealId }, body: { checklist_state: { 'p1.3': 'Complete' } } },
    { id: 'activity', group: 'Deals', method: 'GET', path: '/api/deals/:id/activity/', title: 'FUB activity on the deal', params: { id: pf.dealId } },

    // ---- Drafts ----
    { id: 'drafts', group: 'Drafts', method: 'GET', path: '/api/drafts/', title: 'Resumable packets (own / team)' },
    { id: 'draft-save', group: 'Drafts', method: 'POST', path: '/api/drafts/', title: 'Save (upsert) a draft', body: { id: '00000000-0000-4000-8000-000000000001', title: pf.address, source: 'web', device: 'web', payload: { form: { propertyAddress: pf.address }, re14: {}, agency: {}, forms: ['re_21', 're_14', 'agency_disclosure'], listing: null } } },
    { id: 'draft-delete', group: 'Drafts', method: 'DELETE', path: '/api/drafts/:draft_id/', title: 'Delete a draft', params: { draft_id: '00000000-0000-4000-8000-000000000001' }, danger: 'Deletes the draft.' },

    // ---- Documents ----
    { id: 'docs', group: 'Documents', method: 'GET', path: '/api/deals/:id/documents/', title: 'Document trail', params: { id: pf.dealId } },
    { id: 'doc-upload', group: 'Documents', method: 'POST', path: '/api/deals/:id/documents/', title: 'Upload a document (multipart)', params: { id: pf.dealId }, note: 'Multipart form: file (PDF), doc_type (re_13|re_10|other), direction. Use the deal page dropzone; this explorer sends JSON only.', body: { doc_type: 're_13', direction: 'received' } },
    { id: 'doc-patch', group: 'Documents', method: 'PATCH', path: '/api/deals/:id/documents/:doc_id/', title: 'Set document status', params: { id: pf.dealId, doc_id: pf.docId }, body: { status: 'rejected' } },
    { id: 'doc-delete', group: 'Documents', method: 'DELETE', path: '/api/deals/:id/documents/:doc_id/', title: 'Delete document', params: { id: pf.dealId, doc_id: pf.docId }, danger: 'Deletes the document and its files.' },
    { id: 'doc-send', group: 'Documents', method: 'POST', path: '/api/deals/:id/documents/send/', title: 'Send RE-13 for signature', params: { id: pf.dealId }, body: { doc_type: 're_13', fields: { isSellerCounter: true, counterOfferText: 'Test counter terms.', offerExpirationTime: '5:00 PM' }, resulting_terms: {} }, danger: 'Sends a REAL DocuSign envelope to the deal\'s buyer.' },
    { id: 'doc-accept', group: 'Documents', method: 'POST', path: '/api/deals/:id/documents/send/', title: 'Accept received counter as-is', params: { id: pf.dealId }, body: { doc_type: 're_13', fields: {}, source_document_id: Number(pf.docId) || 0 }, danger: 'Sends the received PDF to the buyer via DocuSign.' },

    // ---- Packet ----
    { id: 'preview-doc', group: 'Packet', method: 'POST', path: '/api/auth/documents/preview/:doc_type/', title: 'Render one form (PDF)', binary: true, params: { doc_type: 're_21' }, body: { propertyAddress: pf.address, buyerName: 'John Doe', buyerEmail: pf.email, buyerPhone: '2085550100', sellerName: 'Jane Seller', offerPrice: 350000, earnestMoney: 5000, financingType: 'conventional', inspectionPeriod: 10, closingDate: new Date(Date.now() + 35 * 86400_000).toISOString() } },
    { id: 'preview-bundle', group: 'Packet', method: 'POST', path: '/api/documents/preview-bundle/', title: 'Render the packet (merged PDF)', binary: true, body: { buyers: [{ name: 'John Doe', email: pf.email }], re21: { propertyAddress: pf.address, buyerName: 'John Doe', buyerEmail: pf.email, sellerName: 'Jane Seller', offerPrice: 350000 }, re14: { propertyAddress: pf.address, buyerName: 'John Doe', propertyType: 'residential,land', searchCity: 'Rexburg, Idaho Falls', agencyType: 'dual' }, agencyDisclosure: { buyerName: 'John Doe' } } },
    { id: 'send-bundle', group: 'Packet', method: 'POST', path: '/api/auth/documents/send/re_21/', title: 'Send packet for signature (creates a deal)', note: 'Idempotent: send_key (or draft_id) — a retry with the same key returns the existing deal. If the deal cannot be saved the envelope is voided and 502 {retryable:true} is returned.', body: { send_key: 'explorer-' + Date.now(), is_test: true, buyers: [{ name: 'John Doe', email: pf.email }], re21: { propertyAddress: pf.address, buyerName: 'John Doe', buyerEmail: pf.email, buyerPhone: '2085550100', sellerName: 'Jane Seller', offerPrice: 350000, closingDate: new Date(Date.now() + 35 * 86400_000).toISOString() }, re14: { propertyAddress: pf.address, buyerName: 'John Doe' }, agencyDisclosure: { buyerName: 'John Doe' } }, danger: 'Sends a REAL DocuSign envelope and creates a deal in the pipeline.' },
    { id: 'contract-status', group: 'Packet', method: 'GET', path: '/api/contracts/status/:envelope_id/', title: 'Envelope status (DocuSign)', params: { envelope_id: pf.envelopeId } },
    { id: 'distribute', group: 'Packet', method: 'POST', path: '/api/auth/api/documents/distribute/', title: 'Email executed RE-21 to title / lender', body: { envelope_id: pf.envelopeId, property_address: pf.address, title_email: pf.email, lender_email: '' }, danger: 'Sends real emails with the executed document.' },
    { id: 'ds-webhook', group: 'Packet', method: 'POST', path: '/api/contracts/webhook/', title: 'DocuSign Connect webhook (simulate)', noAuth: true, body: { event: 'envelope-completed', data: { envelopeId: pf.envelopeId, envelopeSummary: { envelopeDocuments: [] } } }, note: 'Without PDFBytes the server answers 400 — useful to confirm the route is alive.' },

    // ---- MLS ----
    { id: 'mls-search', group: 'MLS', method: 'GET', path: '/api/mls/search/', title: 'Search by address / city', query: { address: 'Rexburg' } },
    { id: 'mls-listing', group: 'MLS', method: 'GET', path: '/api/mls/listing/:mls_number/', title: 'Listing by MLS number', params: { mls_number: '2166543' } },

    // ---- Follow Up Boss ----
    { id: 'fub-connect', group: 'Follow Up Boss', method: 'GET', path: '/api/auth/fub/connect-url/', title: 'OAuth connect URL' },
    { id: 'fub-status', group: 'Follow Up Boss', method: 'GET', path: '/api/auth/fub/status/', title: 'Connection status' },
    { id: 'fub-disconnect', group: 'Follow Up Boss', method: 'DELETE', path: '/api/auth/fub/status/', title: 'Disconnect FUB', danger: 'Clears your FUB tokens.' },
    { id: 'fub-backfill', group: 'Follow Up Boss', method: 'POST', path: '/api/auth/fub/backfill/', title: 'Backfill deals to FUB', body: {}, danger: 'Posts notes to FUB for unsynced deals.' },
    { id: 'fub-hooks', group: 'Follow Up Boss', method: 'GET', path: '/api/auth/fub/webhooks/', title: 'Registered inbound listeners' },
    { id: 'fub-hooks-register', group: 'Follow Up Boss', method: 'POST', path: '/api/auth/fub/webhooks/', title: 'Register inbound listeners', body: { user_id: pf.userId }, danger: 'Creates webhooks on the FUB account.' },
    { id: 'fub-webhook', group: 'Follow Up Boss', method: 'POST', path: '/api/auth/fub/webhook/:token/', title: 'FUB event delivery (simulate)', noAuth: true, params: { token: pf.fubToken || '<signed-account-token>' }, body: { eventId: 'test', eventCreated: new Date().toISOString(), event: 'notesCreated', resourceIds: [1], uri: 'https://api.followupboss.com/v1/notes/1' } },
    { id: 'fub-send', group: 'Follow Up Boss', method: 'POST', path: '/api/auth/fub/send/', title: 'Send a document note to FUB', body: { buyer_name: 'John Doe', buyer_email: pf.email, subject: 'Test from API explorer', body_html: '<p>Hello from Docuflow</p>' }, danger: 'Posts a note to FUB.' },

    // ---- Defaults ----
    { id: 'defaults', group: 'Defaults', method: 'GET', path: '/api/defaults/', title: 'My effective defaults (team ⊕ mine ⊕ locked)' },
    { id: 'defaults-mine', group: 'Defaults', method: 'PATCH', path: '/api/defaults/', title: 'Save my defaults', body: { mine: { inspectionPeriod: 10, titleCompany: 'Pioneer Title Company' } } },
    { id: 'team-defaults', group: 'Defaults', method: 'GET', path: '/api/team/defaults/', title: 'Team defaults (admin)' },
    { id: 'team-defaults-patch', group: 'Defaults', method: 'PATCH', path: '/api/team/defaults/', title: 'Set team defaults (admin; null removes)', body: { defaults: { cancellationPercentage: '$1,000', titleCompanyName: 'Pioneer Title Company', titleEmail: 'orders@pioneertitle.com' } }, danger: 'Locks these values for every agent on the team.' },

    // ---- Team ----
    { id: 'team', group: 'Team', method: 'GET', path: '/api/team/', title: 'My team + members', query: { team: pf.teamId } },
    { id: 'team-rename', group: 'Team', method: 'PATCH', path: '/api/team/', title: 'Rename team', body: { name: 'REAL BROKER LLC' } },
    { id: 'team-invite', group: 'Team', method: 'POST', path: '/api/team/members/', title: 'Invite member', body: { email: 'new.agent@example.com', first_name: 'New', last_name: 'Agent', role: 'agent' }, danger: 'Creates a user and emails them.' },
    { id: 'team-member', group: 'Team', method: 'PATCH', path: '/api/team/members/:user_id/', title: 'Update member', params: { user_id: pf.otherUserId }, body: { role: 'agent', is_active: true } },

    // ---- Developer ----
    { id: 'dev-settings', group: 'Developer', method: 'GET', path: '/api/dev/settings/', title: 'Runtime settings + DocuSign status' },
    { id: 'dev-settings-patch', group: 'Developer', method: 'PATCH', path: '/api/dev/settings/', title: 'Set runtime setting', body: { settings: { docusign_env: 'demo' } }, danger: 'Changes live configuration.' },
    { id: 'dev-ds-test', group: 'Developer', method: 'POST', path: '/api/dev/docusign/test/', title: 'DocuSign connection test', body: { env: 'demo' } },
    { id: 'dev-teams', group: 'Developer', method: 'GET', path: '/api/dev/teams/', title: 'All teams' },
    { id: 'dev-team-create', group: 'Developer', method: 'POST', path: '/api/dev/teams/', title: 'Create team', body: { name: 'Test Team', plan_type: 'basic' }, danger: 'Creates a team.' },
    { id: 'dev-team-patch', group: 'Developer', method: 'PATCH', path: '/api/dev/teams/:team_id/', title: 'Update team', params: { team_id: pf.teamId }, body: { plan_type: 'pro' } },
    { id: 'dev-test-deals', group: 'Developer', method: 'GET', path: '/api/dev/test-deals/', title: 'Test deals (platform-wide)' },
    { id: 'dev-test-deals-purge', group: 'Developer', method: 'POST', path: '/api/dev/test-deals/purge/', title: 'Purge ALL test deals', body: {}, danger: 'Deletes every test deal, voids their envelopes, removes their files.' },
    { id: 'dev-users', group: 'Developer', method: 'GET', path: '/api/dev/users/', title: 'All users' },
    { id: 'dev-user-create', group: 'Developer', method: 'POST', path: '/api/dev/users/', title: 'Create user', body: { email: 'new.agent@example.com', first_name: 'New', last_name: 'Agent', role: 'agent', organization: pf.teamId }, danger: 'Creates a user.' },
    { id: 'dev-user-patch', group: 'Developer', method: 'PATCH', path: '/api/dev/users/:user_id/', title: 'Update user (role, team, DocuSign env…)', params: { user_id: pf.otherUserId }, body: { docusign_production: false } },
    { id: 'dev-user-delete', group: 'Developer', method: 'DELETE', path: '/api/dev/users/:user_id/', title: 'Delete user', params: { user_id: pf.otherUserId }, body: { confirm_deals: false }, danger: 'Permanently deletes that user.' },
  ]
}
