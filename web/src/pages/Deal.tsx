import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Deal, type DealDocument, type DealState, type Me } from '../api'
import { PHASES, STATUSES, isDone } from '../checklist'
import { computeDeadlines, urgency } from '../deadlines'
import CounterForm from '../components/CounterForm'

/** The document a checklist step produced or works from — same mapping as the iOS app. */
function documentForTask(key: string, deal: Deal, docs: DealDocument[]): { title: string; url: string } | null {
  if (['p1.1', 'p1.2', 'p1.3', 'p1.4'].includes(key)) {
    const url = deal.signed_pdf_url || deal.draft_pdf_url
    return url ? { title: 'View Packet', url } : null
  }
  if (key === 'p3.1' || key === 'p3.2') {
    const re10s = docs.filter((d) => d.doc_type === 're_10').sort((a, b) => a.sequence - b.sequence)
    const d = re10s[key === 'p3.1' ? 0 : 1]
    const url = d && (d.signed_pdf_url || d.pdf_url)
    return url ? { title: 'View RE-10', url } : null
  }
  return null
}

export default function DealPage({ me }: { me: Me }) {
  const id = Number(useParams().id)
  const [deal, setDeal] = useState<Deal | null>(null)
  const [state, setState] = useState<DealState | null>(null)
  const [docs, setDocs] = useState<DealDocument[]>([])
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [uploadType, setUploadType] = useState<'other' | 're_13'>('other')
  const fileInput = useRef<HTMLInputElement>(null)
  const [showCounter, setShowCounter] = useState<'respond' | 'new' | null>(null)

  const loadDocs = useCallback(() => api.documents(id).then(setDocs), [id])

  useEffect(() => {
    Promise.all([api.deal(id), api.dealState(id), api.documents(id)])
      .then(([d, s, docs]) => { setDeal(d); setState(s); setDocs(docs) })
      .catch((e) => setError(String(e)))
  }, [id])

  async function setStatus(key: string, status: string) {
    if (!state) return
    // Optimistic — the server merges by key, so this can't clobber the phone.
    setState({ ...state, checklist_state: { ...state.checklist_state, [key]: status } })
    try { await api.patchChecklist(id, { [key]: status }) } catch (e) { setError(String(e)) }
  }

  async function upload(files: FileList | File[]) {
    const list = Array.from(files).filter((f) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'))
    if (list.length === 0) { setError('Only PDF files can be added to a deal.'); return }
    setUploading(true); setError(null)
    try { for (const f of list) await api.uploadDocument(id, f, uploadType); await loadDocs() }
    catch (e) { setError(String(e)) } finally { setUploading(false) }
  }

  if (error && !deal) return <p className="error">{error}</p>
  if (!deal || !state) return <p className="muted">Loading deal…</p>

  const counter = docs.find((d) => d.doc_type === 're_13' && d.direction === 'received' && d.status === 'received')
  const teamView = me.role !== 'agent'

  return (
    <>
      <p><Link to="/">← Pipeline</Link></p>
      <div className="pagehead">
        <div>
          <h1>{deal.property_address}</h1>
          <p className="muted">Buyer: {deal.buyer_names}{teamView && <> · Agent: <b>{deal.agent_name}</b></>} · {deal.status_display}</p>
        </div>
      </div>

      {counter && (
        <div className="banner">
          <div><b>{counter.title} received</b> — <a className="inv" href={counter.signed_pdf_url || counter.pdf_url || '#'} target="_blank" rel="noreferrer">open the counter offer →</a></div>
          <div className="row">
            <button className="link inv" onClick={async () => { if (!confirm('Mark this counter as rejected? The banner goes away; the document stays.')) return; await api.patchDocument(id, counter.id, 'rejected'); await loadDocs() }}>Mark rejected</button>
            <button className="primary inv" onClick={() => setShowCounter('respond')}>Respond</button>
          </div>
        </div>
      )}

      {(() => { const dl = computeDeadlines(deal); return dl.length > 0 ? (
        <section className="card" style={{ marginBottom: 20 }}>
          <h2>Key Deadlines</h2>
          <div className="deadlines">
            {dl.map((x) => { const u = urgency(x.date); return (
              <div className="dl" key={x.title}><span>{x.title}<span className="muted small"> · {x.note}</span></span><span className={`status ${u === 'overdue' ? 'bad' : u === 'soon' ? 'warn' : ''}`}>{x.date.toLocaleDateString()}</span></div>
            )})}
          </div>
        </section>
      ) : null })()}

      {showCounter && (
        <CounterForm
          deal={deal}
          mode={showCounter}
          received={showCounter === 'respond' ? counter : undefined}
          nextNumber={docs.filter((d) => d.doc_type === 're_13').length + 1}
          onClose={() => setShowCounter(null)}
          onSent={async () => { setShowCounter(null); await loadDocs(); setDeal(await api.deal(id)) }}
        />
      )}

      <div className="grid">
        <section className="card">
          <h2>Checklist</h2>
          {PHASES.map((phase) => {
            const done = phase.tasks.filter((t) => isDone(state.checklist_state[t.key] || 'Not Started')).length
            return (
              <div className="phase" key={phase.title}>
                <h3>{phase.title} <span className="muted">{done}/{phase.tasks.length}</span></h3>
                {phase.tasks.map((t) => {
                  const s = state.checklist_state[t.key] || 'Not Started'
                  const doc = documentForTask(t.key, deal, docs)
                  return (
                    <div className={`task ${isDone(s) ? 'done' : ''}`} key={t.key}>
                      <label className="check"><input type="checkbox" checked={isDone(s)} onChange={(e) => setStatus(t.key, e.target.checked ? 'Complete' : 'Not Started')} /><span>{t.title}</span>
                        {doc && <a className="docbtn" href={doc.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>{doc.title}</a>}
                      </label>
                      <select value={s} onChange={(e) => setStatus(t.key, e.target.value)}>
                        {STATUSES.map((o) => <option key={o}>{o}</option>)}
                      </select>
                    </div>
                  )
                })}
              </div>
            )
          })}
        </section>

        <section className="card">
          <div className="cardhead"><h2>Documents</h2><button className="link" onClick={() => setShowCounter('new')}>+ Send a counter offer (RE-13)</button></div>
          <div className="doclist">
            {deal.signed_pdf_url && <a className="doc ok" href={deal.signed_pdf_url} target="_blank" rel="noreferrer"><b>Executed Packet</b><span>Signed by all parties</span></a>}
            {deal.signed_re21_url && <a className="doc ok" href={deal.signed_re21_url} target="_blank" rel="noreferrer"><b>Executed RE-21</b><span>Title &amp; lender copy (RE-21 only)</span></a>}
            {deal.draft_pdf_url && <a className="doc" href={deal.draft_pdf_url} target="_blank" rel="noreferrer"><b>Offer Packet</b><span>As sent for signature</span></a>}
            {docs.map((d) => {
              const forwardable = d.doc_type === 're_13' && d.direction === 'sent' && d.status === 'signed'
              const mailto = `mailto:${deal.listing_agent_email || ''}?subject=${encodeURIComponent(`${d.title} — ${deal.property_address}`)}&body=${encodeURIComponent(`Please find the buyer-signed ${d.title} for ${deal.property_address} for your seller's signature.\n\nSigned counter offer: ${d.signed_pdf_url || ''}\n\nThank you,`)}`
              return (
                <div className={`doc ${d.doc_type === 're_13' ? 'warn' : ''} ${d.status === 'rejected' ? 'muted' : ''}`} key={d.id}>
                  <a href={d.signed_pdf_url || d.pdf_url || '#'} target="_blank" rel="noreferrer"><b>{d.title}</b></a>
                  <span>{d.direction === 'received' ? 'Received' : 'Sent'} · {d.status.replace(/_/g, ' ')} · {new Date(d.created_at).toLocaleDateString()}</span>
                  {forwardable && <a className="fwd" href={mailto}>✉ Send to listing agent{deal.listing_agent_name ? ` (${deal.listing_agent_name})` : ''} →</a>}
                </div>
              )
            })}
            {!deal.signed_pdf_url && !deal.draft_pdf_url && docs.length === 0 && <p className="muted">No documents yet.</p>}
          </div>

          <div
            className={`dropzone ${dragOver ? 'over' : ''}`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files) }}
            onClick={() => fileInput.current?.click()}
          >
            <input ref={fileInput} type="file" accept="application/pdf" multiple hidden onChange={(e) => e.target.files && upload(e.target.files)} />
            <p><b>{uploading ? 'Uploading…' : 'Drop PDFs here'}</b> or click to choose</p>
            <label onClick={(e) => e.stopPropagation()}>
              Add as{' '}
              <select value={uploadType} onChange={(e) => setUploadType(e.target.value as 'other' | 're_13')}>
                <option value="other">Other document</option>
                <option value="re_13">Counter offer (received)</option>
              </select>
            </label>
          </div>
          {error && <p className="error">{error}</p>}
        </section>
      </div>
    </>
  )
}
