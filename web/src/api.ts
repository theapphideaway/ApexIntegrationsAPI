// Thin client for the existing Django REST API. Same origin as the portal,
// JWT in localStorage, silent refresh on 401 (mirrors the iOS AuthManager).

const ACCESS = 'portal_access'
const REFRESH = 'portal_refresh'

export type Me = { id: string; email: string; first_name: string; last_name: string; role: 'admin' | 'tc' | 'agent'; organization: string | null }
export type Deal = {
  id: number; agent_id: string; agent_name: string; property_address: string; buyer_names: string
  status: string; status_display: string; docusign_envelope_id: string | null
  draft_pdf_url: string | null; signed_pdf_url: string | null; is_archived: boolean
  acceptance_date: string | null; updated_at: string
}
export type DealDocument = {
  id: number; doc_type: string; title: string; direction: 'received' | 'sent'; sequence: number
  status: string; pdf_url: string | null; signed_pdf_url: string | null; created_at: string
}
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
  const r = await fetch(path, { ...init, headers })
  if (r.status === 401 && retry && (await refresh())) return request<T>(path, init, false)
  if (r.status === 401) { auth.clear(); window.location.href = '/portal/login'; throw new Error('Session expired') }
  if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`))
  if (r.status === 204) return undefined as T
  return r.json()
}

export const api = {
  requestOtp: (email: string) => request<{ message: string }>('/api/auth/request-otp/', { method: 'POST', body: JSON.stringify({ email }) }),
  verifyOtp: (email: string, code: string) => request<{ access: string; refresh: string; user_id: string }>('/api/auth/verify-otp/', { method: 'POST', body: JSON.stringify({ email, code }) }),
  me: () => request<Me>('/api/auth/users/me/'),
  deals: () => request<Deal[]>('/api/deals/'),
  deal: (id: number) => request<Deal>(`/api/deals/${id}/`),
  setArchived: (id: number, archived: boolean) => request(`/api/deals/${id}/archive/`, { method: 'POST', body: JSON.stringify({ archived }) }),
  dealState: (id: number) => request<DealState>(`/api/deals/${id}/state/`),
  patchChecklist: (id: number, statuses: Record<string, string>) => request<DealState>(`/api/deals/${id}/state/`, { method: 'PATCH', body: JSON.stringify({ checklist_state: statuses }) }),
  documents: (id: number) => request<DealDocument[]>(`/api/deals/${id}/documents/`),
  uploadDocument: (id: number, file: File, docType: string) => {
    const form = new FormData()
    form.append('file', file); form.append('doc_type', docType); form.append('direction', 'received')
    return request<DealDocument>(`/api/deals/${id}/documents/`, { method: 'POST', body: form })
  },
}
