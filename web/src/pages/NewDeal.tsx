import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Me } from '../api'
import { toListing, money, type Listing } from '../mls'
import { SECTIONS, RE14_FIELDS, AGENCY_FIELDS, defaultRE21, defaultRE14, defaultAgency, prefillFromListing, applyLoanTypePresets, missingRequired, buildPacket, type Field, type RE21, type Forms } from '../re21'

type Step = 'search' | 'review' | 'preview'

export default function NewDeal({ me }: { me: Me }) {
  const navigate = useNavigate()
  const [step, setStep] = useState<Step>('search')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Listing[] | null>(null)
  const [searching, setSearching] = useState(false)
  const [listing, setListing] = useState<Listing | null>(null)
  const [form, setForm] = useState<RE21>(defaultRE21())
  const [re14, setRe14] = useState<Record<string, string>>(defaultRE14())
  const [agency, setAgency] = useState<Record<string, string>>(defaultAgency())
  const [forms, setForms] = useState<Forms>({ re21: true, re14: true, agency: true })
  const [tab, setTab] = useState<'re21' | 're14' | 'agency'>('re21')
  const [open, setOpen] = useState<Record<string, boolean>>({ propertyInformation: true, buyerSeller: true, financialTerms: true, timelineCompanies: true })
  const [showMissing, setShowMissing] = useState(false)
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const searchBox = useRef<HTMLInputElement>(null)

  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl) }, [pdfUrl])

  // ---- Step 1: MLS number or address ----
  async function search(e?: React.FormEvent) {
    e?.preventDefault()
    const q = query.trim(); if (!q) return
    setSearching(true); setError(null); setResults(null)
    try {
      let found: Listing[] = []
      if (/^[A-Za-z]?\d{4,}$/.test(q)) {           // looks like an MLS number → exact lookup first
        try { found = (await api.mlsListing(q)).value.map(toListing) } catch { found = [] }
      }
      if (found.length === 0) found = (await api.mlsSearch(q)).value.map(toListing)
      setResults(found)
      searchBox.current?.blur()
    } catch (err) { setError(String(err)) } finally { setSearching(false) }
  }

  function choose(l: Listing) {
    setListing(l)
    const f = applyLoanTypePresets(prefillFromListing(defaultRE21(), l))
    setForm(f)
    setRe14((r) => ({ ...r, searchCity: l.city, searchCounty: l.countyOrParish || '', searchState: l.stateOrProvince || 'Idaho' }))
    setStep('review'); window.scrollTo(0, 0)
  }

  // ---- Step 2: review ----
  const missing = useMemo(() => missingRequired(form), [form])
  const set = (key: string, value: unknown) => setForm((f) => {
    const next = { ...f, [key]: value }
    return key === 'financingType' ? applyLoanTypePresets(next) : next
  })

  async function preview() {
    if (missing.length) { setShowMissing(true); return }
    setBusy('preview'); setError(null)
    try {
      const blob = await api.previewBundle(buildPacket(form, re14, agency, forms))
      if (pdfUrl) URL.revokeObjectURL(pdfUrl)
      setPdfUrl(URL.createObjectURL(blob)); setStep('preview'); window.scrollTo(0, 0)
    } catch (err) { setError(String(err)) } finally { setBusy(null) }
  }

  async function send() {
    const names = [form.buyerName, form.buyerNameTwo].filter(Boolean).join(' & ')
    if (!confirm(`Send the packet to ${names} (${form.buyerEmail}${form.buyerEmailTwo ? ', ' + form.buyerEmailTwo : ''}) for signature via DocuSign ${me.docusign_env === 'production' ? 'PRODUCTION' : 'TEST'}?`)) return
    setBusy('send'); setError(null)
    try {
      const r = await api.sendPacket(buildPacket(form, re14, agency, forms))
      navigate(`/deals/${r.deal_id}`)
    } catch (err) { setError(String(err)) } finally { setBusy(null) }
  }

  const selectedCount = Object.values(forms).filter(Boolean).length

  // ---------------- render ----------------
  if (step === 'search') return (
    <>
      <div className="pagehead"><div><h1>New Deal · Start from property</h1><p className="muted">Search the live MLS by address, city, or MLS number. The listing prefills the RE-21.</p></div></div>
      <form className="searchbar" onSubmit={search}>
        <input ref={searchBox} autoFocus placeholder="431 S 3rd W, Rexburg, or MLS #2166543" value={query} onChange={(e) => setQuery(e.target.value)} />
        <button className="primary" disabled={searching || !query.trim()}>{searching ? 'Searching…' : 'Search MLS'}</button>
      </form>
      {error && <p className="error">{error}</p>}
      {results && results.length === 0 && <p className="muted">No active listing matches “{query}”. Try the street address without unit numbers, or the city name.</p>}
      {results && results.length > 0 && (
        <div className="listings">
          {results.map((l) => (
            <button type="button" className="listing" key={l.mlsNumber} onClick={() => choose(l)}>
              {l.thumbnailURL ? <img src={l.thumbnailURL} alt="" /> : <div className="nophoto">No photo</div>}
              <div className="lbody">
                <b>{l.unparsedAddress}</b>
                <span>{l.city}, {l.stateOrProvince} {l.postalCode}</span>
                <span className="lprice">{money(l.listPrice)} <span className="muted small">· {l.bedroomsTotal ?? '–'} bd · {l.bathroomsTotal ?? '–'} ba · {l.livingArea ? l.livingArea.toLocaleString() + ' sqft' : '–'}</span></span>
                <span className="muted small">MLS #{l.mlsNumber} · {l.standardStatus || ''} {l.listAgentFullName ? `· Listed by ${l.listAgentFullName}` : ''}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </>
  )

  if (step === 'preview') return (
    <>
      <div className="pagehead">
        <div><h1>Packet Preview</h1><p className="muted">{listing?.unparsedAddress} · {selectedCount} document{selectedCount === 1 ? '' : 's'}</p></div>
        <div className="filters">
          <button className="link" onClick={() => setStep('review')}>← Edit values</button>
          <button className="primary" disabled={busy !== null} onClick={send}>{busy === 'send' ? 'Sending…' : 'Send for Signatures'}</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {pdfUrl && <iframe className="pdf" src={pdfUrl} title="Packet preview" />}
    </>
  )

  return (
    <>
      <div className="pagehead">
        <div><h1>Review Packet</h1><p className="muted">{listing?.unparsedAddress} · MLS #{listing?.mlsNumber} · agent {me.first_name} {me.last_name}</p></div>
        <div className="filters"><button className="link" onClick={() => setStep('search')}>← Different property</button></div>
      </div>

      <div className="pills">
        {([['re21', 'RE-21 Purchase Agreement'], ['re14', 'RE-14 Buyer Rep'], ['agency', 'Agency Disclosure']] as const).map(([k, label]) => (
          <button key={k} type="button" className={`pillbtn ${forms[k] ? 'on' : ''}`} onClick={() => setForms((f) => ({ ...f, [k]: !f[k] }))}>{forms[k] ? '✓ ' : ''}{label}</button>
        ))}
        <span className="muted small">Tap to include/exclude from the packet</span>
      </div>

      <div className="tabs">
        {([['re21', 'RE-21'], ['re14', 'RE-14'], ['agency', 'Agency Disc.']] as const).map(([k, label]) => (
          <button key={k} type="button" className={`tab ${tab === k ? 'active' : ''}`} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === 're21' && SECTIONS.map((s) => {
        const miss = missing.filter((m) => m.section === s.title).length
        const isOpen = open[s.id] ?? false
        return (
          <section className="card section" key={s.id}>
            <button type="button" className="sechead" onClick={() => setOpen((o) => ({ ...o, [s.id]: !isOpen }))}>
              <span>{isOpen ? '▾' : '▸'} {s.title}</span>
              {miss > 0 ? <span className="status bad">{miss} required</span> : <span className="status ok">complete</span>}
            </button>
            {isOpen && <FieldGrid fields={s.fields} values={form} onChange={set} showMissing={showMissing} />}
          </section>
        )
      })}
      {tab === 're14' && (
        <section className="card section"><p className="muted small">Buyer Representation Agreement. Buyers, agent and property come from the RE-21; these are only what the RE-14 adds.</p>
          <FieldGrid fields={RE14_FIELDS} values={re14} onChange={(k, v) => setRe14((r) => ({ ...r, [k]: String(v ?? '') }))} showMissing={false} /></section>
      )}
      {tab === 'agency' && (
        <section className="card section"><p className="muted small">Leave blank to use your brokerage profile on file.</p>
          <FieldGrid fields={AGENCY_FIELDS} values={agency} onChange={(k, v) => setAgency((a) => ({ ...a, [k]: String(v ?? '') }))} showMissing={false} /></section>
      )}

      {showMissing && missing.length > 0 && (
        <div className="card warnbox"><b>Almost there</b> — fill in: {missing.map((m) => `${m.label} (${m.section})`).join(', ')}</div>
      )}
      {error && <p className="error">{error}</p>}
      <div className="actionbar">
        <span className="muted small">{missing.length === 0 ? 'All required fields complete.' : `${missing.length} required field${missing.length === 1 ? '' : 's'} remaining`}</span>
        <button className="primary" disabled={busy !== null || selectedCount === 0} onClick={preview}>{busy === 'preview' ? 'Generating…' : 'Generate PDF'}</button>
      </div>
    </>
  )
}

function FieldGrid({ fields, values, onChange, showMissing }: { fields: Field[]; values: Record<string, unknown>; onChange: (k: string, v: unknown) => void; showMissing: boolean }) {
  const groups: { name: string | undefined; fields: Field[] }[] = []
  for (const f of fields) { const g = groups[groups.length - 1]; if (g && g.name === f.group) g.fields.push(f); else groups.push({ name: f.group, fields: [f] }) }
  return (
    <>
      {groups.map((g, i) => (
        <div key={i} className={g.name ? 'fgroup' : 'fplain'}>
          {g.name && <div className="fgname">{g.name}</div>}
          <div className="fgrid">{g.fields.map((f) => <FieldInput key={f.key} f={f} value={values[f.key]} onChange={(v) => onChange(f.key, v)} invalid={showMissing && !!f.required && (values[f.key] === undefined || values[f.key] === null || values[f.key] === '')} />)}</div>
        </div>
      ))}
    </>
  )
}

function FieldInput({ f, value, onChange, invalid }: { f: Field; value: unknown; onChange: (v: unknown) => void; invalid: boolean }) {
  const cls = invalid ? 'invalid' : ''
  const label = <>{f.label}{f.required && <span className="req"> *</span>}</>
  switch (f.type) {
    case 'toggle': return <label className="check ftoggle"><input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} /><span>{f.label}</span></label>
    case 'select': return <label>{label}<select className={cls} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)}><option value="">—</option>{f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
    case 'textarea': return <label className="wide">{label}<textarea className={cls} rows={3} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} /></label>
    case 'money': return <label>{label}<input className={cls} inputMode="decimal" value={value === undefined || value === null ? '' : String(value)} placeholder="$" onChange={(e) => { const n = e.target.value.replace(/[^0-9.]/g, ''); onChange(n === '' ? null : Number(n)) }} /></label>
    case 'int': return <label>{label}<input className={cls} inputMode="numeric" value={value === undefined || value === null ? '' : String(value)} onChange={(e) => { const n = e.target.value.replace(/[^0-9]/g, ''); onChange(n === '' ? null : Number(n)) }} /></label>
    case 'date': return <label>{label}<input className={cls} type="date" value={typeof value === 'string' ? value.slice(0, 10) : ''} onChange={(e) => onChange(e.target.value || null)} /></label>
    default: return <label>{label}<input className={cls} type={f.type === 'email' ? 'email' : f.type === 'phone' ? 'tel' : 'text'} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} /></label>
  }
}
