import { useEffect, useMemo, useState } from 'react'
import { api, authFetch, type Me } from '../api'
import { catalog, type Endpoint, type Prefill } from '../endpoints'

type Result = { status: number; ms: number; contentType: string; text?: string; json?: unknown; blobUrl?: string; size?: number }

/** Postman-style explorer over every server endpoint, prefilled from live data. */
export default function ApiExplorer({ me }: { me: Me }) {
  const [prefill, setPrefill] = useState<Prefill | null>(null)
  const [selectedId, setSelectedId] = useState<string>('me')
  const [params, setParams] = useState<Record<string, string>>({})
  const [query, setQuery] = useState<Record<string, string>>({})
  const [body, setBody] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('')

  // Prefill ids from what this account can see.
  useEffect(() => {
    (async () => {
      const pf: Prefill = { dealId: '', docId: '', envelopeId: '', userId: me.id, otherUserId: '', teamId: me.organization || '', email: me.email, address: '431 S 3rd W, Rexburg ID 83440', fubToken: '' }
      try {
        const deals = await api.deals()
        const d = deals.find((x) => !x.is_archived) || deals[0]
        if (d) { pf.dealId = String(d.id); pf.envelopeId = d.docusign_envelope_id || ''; pf.address = d.property_address
          try { const docs = await api.documents(d.id); if (docs[0]) pf.docId = String(docs[0].id) } catch { /* none */ } }
      } catch { /* not allowed */ }
      try { const users = await api.dev.users(); const other = users.find((u) => u.id !== me.id); if (other) pf.otherUserId = other.id; if (!pf.teamId && users[0]?.organization) pf.teamId = users[0].organization } catch { /* not superuser */ }
      setPrefill(pf)
    })()
  }, [me])

  const endpoints = useMemo(() => prefill ? catalog(prefill) : [], [prefill])
  const selected = endpoints.find((e) => e.id === selectedId) || endpoints[0]

  useEffect(() => {
    if (!selected) return
    setParams({ ...(selected.params || {}) }); setQuery({ ...(selected.query || {}) })
    setBody(selected.body === undefined ? '' : JSON.stringify(selected.body, null, 2)); setResult(null)
  }, [selected?.id, endpoints]) // eslint-disable-line react-hooks/exhaustive-deps

  const groups = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const out = new Map<string, Endpoint[]>()
    endpoints.filter((e) => !q || `${e.method} ${e.path} ${e.title}`.toLowerCase().includes(q)).forEach((e) => out.set(e.group, [...(out.get(e.group) || []), e]))
    return Array.from(out.entries())
  }, [endpoints, filter])

  if (!selected) return <p className="muted">Loading endpoints…</p>

  const resolvedPath = selected.path.replace(/:(\w+)/g, (_, k) => encodeURIComponent(params[k] ?? ''))
  const qs = Object.entries(query).filter(([, v]) => v !== '').map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&')
  const url = resolvedPath + (qs ? `?${qs}` : '')
  const hasBody = selected.method !== 'GET'

  async function send() {
    if (selected!.danger && !confirm(`${selected!.danger}\n\nSend ${selected!.method} ${url}?`)) return
    setBusy(true); setResult(null)
    const started = performance.now()
    try {
      let parsed: unknown = undefined
      if (hasBody && body.trim()) { try { parsed = JSON.parse(body) } catch { setResult({ status: 0, ms: 0, contentType: '', text: 'Body is not valid JSON.' }); setBusy(false); return } }
      const init: RequestInit = { method: selected!.method, headers: hasBody ? { 'Content-Type': 'application/json' } : {}, body: hasBody && parsed !== undefined ? JSON.stringify(parsed) : undefined }
      const r = selected!.noAuth ? await fetch(url, init) : await authFetch(url, init)
      const ms = performance.now() - started
      const ct = r.headers.get('content-type') || ''
      if (ct.includes('pdf')) { const blob = await r.blob(); setResult({ status: r.status, ms, contentType: ct, blobUrl: URL.createObjectURL(blob), size: blob.size }) }
      else { const text = await r.text(); let json: unknown; try { json = text ? JSON.parse(text) : null } catch { /* text */ } setResult({ status: r.status, ms, contentType: ct, text, json }) }
    } catch (e) { setResult({ status: 0, ms: performance.now() - started, contentType: '', text: String(e) }) }
    finally { setBusy(false) }
  }

  const curl = `curl -X ${selected.method} '${window.location.origin}${url}'${selected.noAuth ? '' : " -H 'Authorization: Bearer <token>'"}${hasBody && body.trim() ? ` -H 'Content-Type: application/json' -d '${body.replace(/\n\s*/g, ' ').replace(/'/g, "\\'")}'` : ''}`

  return (
    <div className="explorer">
      <aside className="eplist">
        <input placeholder="Filter endpoints…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        {groups.map(([group, items]) => (
          <div key={group} className="epgroup">
            <div className="sect">{group}</div>
            {items.map((e) => (
              <button key={e.id} className={`ep ${e.id === selected.id ? 'active' : ''}`} onClick={() => setSelectedId(e.id)}>
                <span className={`method m-${e.method.toLowerCase()}`}>{e.method}</span><span className="eptitle">{e.title}</span>{e.danger && <span className="epdanger" title={e.danger}>!</span>}
              </button>
            ))}
          </div>
        ))}
      </aside>

      <section className="epmain">
        <div className="card">
          <div className="cardhead"><h2>{selected.title}</h2><span className="muted small">{selected.group}{selected.noAuth ? ' · no auth' : ' · bearer token'}</span></div>
          <div className="urlbar">
            <span className={`method m-${selected.method.toLowerCase()}`}>{selected.method}</span>
            <code className="urlpath">{url}</code>
            <button className="primary" disabled={busy} onClick={send}>{busy ? 'Sending…' : 'Send'}</button>
          </div>
          {selected.note && <p className="muted small">{selected.note}</p>}
          {selected.danger && <p className="warnbox card" style={{ padding: '8px 12px' }}>⚠ {selected.danger} You&apos;ll be asked to confirm.</p>}

          {Object.keys(params).length > 0 && (
            <div className="kv"><div className="fgname">Path parameters</div>
              {Object.keys(params).map((k) => <label key={k}>{k}<input value={params[k]} onChange={(e) => setParams({ ...params, [k]: e.target.value })} /></label>)}
            </div>
          )}
          {Object.keys(query).length > 0 && (
            <div className="kv"><div className="fgname">Query</div>
              {Object.keys(query).map((k) => <label key={k}>{k}<input value={query[k]} onChange={(e) => setQuery({ ...query, [k]: e.target.value })} /></label>)}
            </div>
          )}
          {hasBody && (
            <div className="kv"><div className="fgname">Body (JSON)</div>
              <textarea className="code" rows={Math.min(22, Math.max(4, body.split('\n').length + 1))} value={body} onChange={(e) => setBody(e.target.value)} spellCheck={false} />
            </div>
          )}
          <details className="curl"><summary className="muted small">cURL</summary><pre className="result">{curl}</pre></details>
        </div>

        <div className="card" style={{ marginTop: 16 }}>
          <div className="cardhead"><h2>Response</h2>{result && <span className="muted small">{result.ms.toFixed(0)} ms · {result.contentType || '—'}{result.size ? ` · ${(result.size / 1024).toFixed(0)} KB` : ''}</span>}</div>
          {!result && <p className="muted small">Send the request to see the response here.</p>}
          {result && (
            <>
              <span className={`status ${result.status >= 200 && result.status < 300 ? 'ok' : result.status >= 400 || result.status === 0 ? 'bad' : 'warn'}`}>{result.status || 'network error'}</span>
              {result.blobUrl ? (
                <div style={{ marginTop: 12 }}><a className="btnlink" href={result.blobUrl} target="_blank" rel="noreferrer">Open PDF</a><iframe className="pdf" style={{ height: 520, marginTop: 12 }} src={result.blobUrl} title="PDF response" /></div>
              ) : (
                <pre className="result" style={{ maxHeight: 520, marginTop: 12 }}>{result.json !== undefined ? JSON.stringify(result.json, null, 2) : result.text}</pre>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  )
}
