// Thin client for the existing Django REST API. Same origin as the portal,
// JWT in localStorage, silent refresh on 401 (mirrors the iOS AuthManager).

const ACCESS = 'portal_access'
const REFRESH = 'portal_refresh'

export type Me = { id: string; email: string; first_name: string; last_name: string; role: 'admin' | 'tc' | 'agent'; organization: string | null; is_superuser?: boolean; docusign_production?: boolean; docusign_env?: 'demo' | 'production' }
export type Team = { id: string; name: string; plan_type: string; is_active: boolean; created_at: string; member_count?: number; deal_count?: number }
export type PortalUser = Me & { phone_number: string | null; organization_name: string | null; deal_count: number; fub_connected: boolean; fub_account_id?: string; is_active: boolean }
export type DevSettings = {
  settings: Record<string, unknown>; defaults: Record<string, unknown>
  docusign: { current: 'demo' | 'production'; master_production: boolean; production_users: number; environments: Record<string, { auth_server: string; base_path: string; client_id_set: boolean; user_id_set: boolean; account_id_set: boolean; private_key_present: boolean; private_key_path: string; configured: boolean }> }
  server: { debug: boolean; db_engine: string }
}

// ---- Console bus: every request/response is published for the dev console ----
export type ConsoleEntry = { id: number; at: Date; method: string; path: string; status: number | string; ms: number; request?: unknown; response?: unknown }
type Listener = (e: ConsoleEntry) => void
const listeners = new Set<Listener>()
let seq = 0
export const consoleBus = {
  subscribe(fn: Listener) { listeners.add(fn); return () => { listeners.delete(fn) } },
  emit(e: Omit<ConsoleEntry, 'id' | 'at'>) { const entry = { ...e, id: ++seq, at: new Date() }; listeners.forEach((l) => l(entry)) },
}
export type Deal = {
  id: number; agent_id: string; agent_name: string; agent_team?: string; property_address: string; buyer_names: string
  listing_agent_email?: string | null; listing_agent_name?: string
  status: string; status_display: string; docusign_envelope_id: string | null
  draft_pdf_url: string | null; signed_pdf_url: string | null; signed_re21_url?: string | null; is_archived: boolean; is_test?: boolean
  acceptance_date: string | null; form_snapshot: Record<string, any> | null; updated_at: string
}
export type DealDocument = {
  id: number; doc_type: string; title: string; direction: 'received' | 'sent'; sequence: number
  status: string; pdf_url: string | null; signed_pdf_url: string | null; created_at: string
}
export type DealActivity = { id: number; source: string; kind: string; title: string; body: string; actor: string; external_url: string; occurred_at: string }
export type Draft = { id: string; agent_id: string; agent_name: string; title: string; source: string; revising_deal_id: number | null; device: string; payload: DraftPayload; created_at: string; updated_at: string }
export type DraftPayload = { form: Record<string, unknown>; re14: Record<string, string>; agency: Record<string, string>; forms: string[]; listing: { mlsNumber?: string; address?: string; listAgentEmail?: string; listAgentName?: string } | null; source?: string }
export type Recipient = { name: string; email: string; status: string; sent_at?: string | null; delivered_at?: string | null; signed_at?: string | null; declined_at?: string | null; declined_reason?: string | null }
export type SigningStatus = { envelope_id?: string; status: string; sent_at?: string | null; completed_at?: string | null; voided_reason?: string | null; recipients: Recipient[]; action: string; deal?: Deal }
export type DealState = { checklist_state: Record<string, string>; form_snapshot: Record<string, unknown> | null; acceptance_date: string | null }

export const auth = {
  get access() { return localStorage.getItem(ACCESS) },
  set(access: string, refresh: string) { localStorage.setItem(ACCESS, access); localStorage.setItem(REFRESH, refresh) },
  clear() { localStorage.removeItem(ACCESS); localStorage.removeItem(REFRESH) },
  get isLoggedIn() { return !!localStorage.getItem(ACCESS) },
}

async function refresh(): Promise<boolean> {
  const token = localStorage.getItem(REFRESH)
  if (!token) return false
  const r = await fetch('/api/token/refresh/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: token }) })
  if (!r.ok) return false
  const data = await r.json()
  localStorage.setItem(ACCESS, data.access)
  return true
}

async function request<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers || {})
  if (auth.access) headers.set('Authorization', `Bearer ${auth.access}`)
  if (!(init.body instanceof FormData) && init.body) headers.set('Content-Type', 'application/json')
  const started = performance.now()
  const method = (init.method || 'GET').toUpperCase()
  let reqBody: unknown = undefined
  if (typeof init.body === 'string') { try { reqBody = JSON.parse(init.body) } catch { reqBody = init.body } }
  else if (init.body instanceof FormData) reqBody = Object.fromEntries(Array.from(init.body.entries()).map(([k, v]) => [k, v instanceof File ? `<file ${v.name} ${v.size}b>` : v]))
  let r: Response
  try { r = await fetch(path, { ...init, headers }) }
  catch (err) { consoleBus.emit({ method, path, status: 'network error', ms: performance.now() - started, request: reqBody, response: String(err) }); throw err }
  if (r.status === 401 && retry && (await refresh())) return request<T>(path, init, false)
  if (r.status === 401) { auth.clear(); window.location.href = '/portal/login'; throw new Error('Session expired') }
  const text = await r.text()
  let parsed: unknown = text
  try { parsed = text ? JSON.parse(text) : null } catch { /* keep text */ }
  consoleBus.emit({ method, path, status: r.status, ms: performance.now() - started, request: reqBody, response: parsed })
  if (!r.ok) {
    const msg = typeof parsed === 'object' && parsed && 'error' in (parsed as object) ? String((parsed as { error: unknown }).error) : text || `HTTP ${r.status}`
    throw new Error(msg)
  }
  if (r.status === 204 || !text) return undefined as T
  return parsed as T
}

/** Raw authenticated fetch (API explorer): adds the bearer token, refreshes once on 401, logs to the console bus, returns the Response untouched. */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const started = performance.now()
  const doFetch = () => {
    const headers = new Headers(init.headers || {})
    if (auth.access) headers.set('Authorization', `Bearer ${auth.access}`)
    return fetch(path, { ...init, headers })
  }
  let r = await doFetch()
  if (r.status === 401 && (await refresh())) r = await doFetch()
  let reqBody: unknown = undefined
  if (typeof init.body === 'string') { try { reqBody = JSON.parse(init.body) } catch { reqBody = init.body } }
  const ct = r.headers.get('content-type') || ''
  let logged: unknown = `<${ct}>`
  if (ct.includes('json')) { try { logged = await r.clone().json() } catch { /* ignore */ } }
  consoleBus.emit({ method: (init.method || 'GET').toUpperCase(), path, status: r.status, ms: performance.now() - started, request: reqBody, response: logged })
  return r
}

/** Binary-returning request (PDF preview). Same auth/refresh rules. */
export async function requestBlob(path: string, body: unknown): Promise<Blob> {
  const started = performance.now()
  const doFetch = () => fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(auth.access ? { Authorization: `Bearer ${auth.access}` } : {}) }, body: JSON.stringify(body) })
  let r = await doFetch()
  if (r.status === 401 && (await refresh())) r = await doFetch()
  consoleBus.emit({ method: 'POST', path, status: r.status, ms: performance.now() - started, request: body, response: r.ok ? `<${r.headers.get('content-type')} ${r.headers.get('content-length') || '?'} bytes>` : await r.clone().text() })
  if (!r.ok) { const t = await r.text(); try { throw new Error(JSON.parse(t).error || t) } catch (e) { throw e instanceof Error ? e : new Error(t) } }
  return r.blob()
}

export const api = {
  // ---- MLS (server-side credential; returns RESO envelopes) ----
  mlsSearch: (address: string) => request<{ value: Record<string, unknown>[] }>(`/api/mls/search/?address=${encodeURIComponent(address)}`),
  mlsListing: (mlsNumber: string) => request<{ value: Record<string, unknown>[] }>(`/api/mls/listing/${encodeURIComponent(mlsNumber)}/`),
  // ---- Packet ----
  previewBundle: (body: unknown) => requestBlob('/api/documents/preview-bundle/', body),
  sendPacket: (body: unknown) => request<{ status: string; envelope_id: string; deal_id: number }>('/api/auth/documents/send/re_21/', { method: 'POST', body: JSON.stringify(body) }),
  requestOtp: (email: string) => request<{ message: string }>('/api/auth/request-otp/', { method: 'POST', body: JSON.stringify({ email }) }),
  verifyOtp: (email: string, code: string) => request<{ access: string; refresh: string; user_id: string }>('/api/auth/verify-otp/', { method: 'POST', body: JSON.stringify({ email, code }) }),
  me: () => request<Me>('/api/auth/users/me/'),
  deals: () => request<Deal[]>('/api/deals/'),
  deal: (id: number) => request<Deal>(`/api/deals/${id}/`),
  setArchived: (id: number, archived: boolean) => request(`/api/deals/${id}/archive/`, { method: 'POST', body: JSON.stringify({ archived }) }),
  dealState: (id: number) => request<DealState>(`/api/deals/${id}/state/`),
  patchChecklist: (id: number, statuses: Record<string, string>) => request<DealState>(`/api/deals/${id}/state/`, { method: 'PATCH', body: JSON.stringify({ checklist_state: statuses }) }),
  documents: (id: number) => request<DealDocument[]>(`/api/deals/${id}/documents/`),
  reconcile: (id: number) => request<SigningStatus>(`/api/deals/${id}/reconcile/`, { method: 'POST', body: '{}' }),
  remind: (id: number) => request<{ ok: boolean }>(`/api/deals/${id}/remind/`, { method: 'POST', body: '{}' }),
  correctRecipient: (id: number, recipientId: string, newEmail: string, newName?: string) => request<{ ok: boolean }>(`/api/deals/${id}/correct-recipient/`, { method: 'POST', body: JSON.stringify({ recipient_id: recipientId, new_email: newEmail, new_name: newName }) }),
  activity: (id: number) => request<DealActivity[]>(`/api/deals/${id}/activity/`),
  fubRegisterWebhooks: (userId?: string) => request<Record<string, string>>('/api/auth/fub/webhooks/', { method: 'POST', body: JSON.stringify(userId ? { user_id: userId } : {}) }),
  sendDocument: (id: number, body: { doc_type: string; fields: Record<string, unknown>; buyers?: { name: string; email: string }[]; resulting_terms?: Record<string, unknown>; source_document_id?: number; send_key?: string }) =>
    request<DealDocument>(`/api/deals/${id}/documents/send/`, { method: 'POST', body: JSON.stringify(body) }),
  // ---- Drafts (resumable packets, any device) ----
  drafts: () => request<Draft[]>('/api/drafts/'),
  draft: (id: string) => request<Draft>(`/api/drafts/${id}/`),
  saveDraft: (body: { id: string; title: string; source: string; payload: DraftPayload; revising_deal_id?: number | null }) => request<Draft>('/api/drafts/', { method: 'POST', body: JSON.stringify({ ...body, device: 'web' }) }),
  deleteDraft: (id: string) => request<void>(`/api/drafts/${id}/`, { method: 'DELETE' }),
  // ---- Contract defaults ----
  defaults: () => request<{ team: Record<string, unknown>; mine: Record<string, unknown>; effective: Record<string, unknown>; locked: string[] }>('/api/defaults/'),
  patchMyDefaults: (mine: Record<string, unknown>) => request<{ team: Record<string, unknown>; mine: Record<string, unknown>; effective: Record<string, unknown>; locked: string[] }>('/api/defaults/', { method: 'PATCH', body: JSON.stringify({ mine }) }),
  // ---- Team admin (role admin; own team only) ----
  team: {
    get: (teamId?: string) => request<{ team: Team; members: PortalUser[]; deal_count: number }>(`/api/team/${teamId ? `?team=${teamId}` : ''}`),
    rename: (name: string) => request<Team>('/api/team/', { method: 'PATCH', body: JSON.stringify({ name }) }),
    invite: (body: { email: string; first_name: string; last_name: string; phone_number?: string; role: string }) => request<PortalUser>('/api/team/members/', { method: 'POST', body: JSON.stringify(body) }),
    patchMember: (id: string, body: Record<string, unknown>) => request<PortalUser>(`/api/team/members/${id}/`, { method: 'PATCH', body: JSON.stringify(body) }),
    defaults: () => request<{ defaults: Record<string, unknown>; locked: string[] }>('/api/team/defaults/'),
    patchDefaults: (defaults: Record<string, unknown>) => request<{ defaults: Record<string, unknown>; locked: string[] }>('/api/team/defaults/', { method: 'PATCH', body: JSON.stringify({ defaults }) }),
  },
  // ---- Developer portal (superuser only) ----
  dev: {
    settings: () => request<DevSettings>('/api/dev/settings/'),
    patchSettings: (settings: Record<string, unknown>) => request<DevSettings>('/api/dev/settings/', { method: 'PATCH', body: JSON.stringify({ settings }) }),
    testDocuSign: (env?: string) => request<Record<string, unknown>>('/api/dev/docusign/test/', { method: 'POST', body: JSON.stringify({ env }) }),
    teams: () => request<Team[]>('/api/dev/teams/'),
    createTeam: (body: { name: string; plan_type?: string }) => request<Team>('/api/dev/teams/', { method: 'POST', body: JSON.stringify(body) }),
    patchTeam: (id: string, body: Partial<Team>) => request<Team>(`/api/dev/teams/${id}/`, { method: 'PATCH', body: JSON.stringify(body) }),
    users: () => request<PortalUser[]>('/api/dev/users/'),
    testDeals: () => request<{ count: number; deals: { id: number; property_address: string; buyer_names: string; status: string; agent: string }[] }>('/api/dev/test-deals/'),
    purgeTestDeals: () => request<{ deleted: number; voided_envelopes: number; errors: string[] }>('/api/dev/test-deals/purge/', { method: 'POST', body: '{}' }),
    createUser: (body: { email: string; first_name: string; last_name: string; phone_number?: string; role: string; organization: string }) => request<PortalUser>('/api/dev/users/', { method: 'POST', body: JSON.stringify(body) }),
    patchUser: (id: string, body: Record<string, unknown>) => request<PortalUser>(`/api/dev/users/${id}/`, { method: 'PATCH', body: JSON.stringify(body) }),
    deleteUser: (id: string, confirmDeals = false) => request<void>(`/api/dev/users/${id}/`, { method: 'DELETE', body: JSON.stringify({ confirm_deals: confirmDeals }) }),
  },
  patchDocument: (id: number, docId: number, status: 'received' | 'rejected' | 'signed') => request<DealDocument>(`/api/deals/${id}/documents/${docId}/`, { method: 'PATCH', body: JSON.stringify({ status }) }),
  uploadDocument: (id: number, file: File, docType: string) => {
    const form = new FormData()
    form.append('file', file); form.append('doc_type', docType); form.append('direction', 'received')
    return request<DealDocument>(`/api/deals/${id}/documents/`, { method: 'POST', body: form })
  },
}
