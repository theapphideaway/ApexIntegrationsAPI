import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type Me, type DraftPayload } from '../api'
import { toListing, money, type Listing } from '../mls'
import { SECTIONS, RE14_FIELDS, AGENCY_FIELDS, defaultRE21, defaultRE14, defaultAgency, prefillFromListing, applyLoanTypePresets, applyDefaults, missingRequired, buildPacket, draftForm, type Field, type RE21, type Forms } from '../re21'

type Step = 'search' | 'review' | 'preview'

export default function NewDeal({ me }: { me: Me }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [step, setStep] = useState<Step>('search')
  // Server-side draft: created when a property is chosen (or resumed from ?draft=), saved on every edit.
  const [draftId, setDraftId] = useState<string | null>(searchParams.get('draft'))
  const [draftSaved, setDraftSaved] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const saveTimer = useRef<number | null>(null)
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
  const [savedDefaults, setSavedDefaults] = useState<{ effective: Record<string, unknown>; locked: string[] }>({ effective: {}, locked: [] })
  useEffect(() => { api.defaults().then((d) => setSavedDefaults({ effective: d.effective, locked: d.locked })).catch(() => {}) }, [])

  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl) }, [pdfUrl])

  // Resume a draft (from the pipeline's Drafts strip, or a phone-started packet).
  useEffect(() => {
    const id = searchParams.get('draft'); if (!id) return
    api.draft(id).then((d) => {
      const pl = d.payload
      setForm({ ...defaultRE21(), ...(pl.form || {}) })
      setRe14({ ...defaultRE14(), ...(pl.re14 || {}) })
      setAgency({ ...defaultAgency(), ...(pl.agency || {}) })
      const f = pl.forms || ['re_21', 're_14', 'agency_disclosure']
      setForms({ re21: f.includes('re_21'), re14: f.includes('re_14'), agency: f.includes('agency_disclosure') })
      if (pl.listing) setListing({ mlsNumber: pl.listing.mlsNumber || '', unparsedAddress: pl.listing.address || String(pl.form?.propertyAddress || ''), city: String(pl.form?.propertyCity || ''), stateOrProvince: String(pl.form?.propertyState || ''), postalCode: String(pl.form?.propertyZip || ''), listAgentEmail: pl.listing.listAgentEmail, listAgentFullName: pl.listing.listAgentName })
      else setListing({ mlsNumber: '', unparsedAddress: String(pl.form?.propertyAddress || ''), city: '', stateOrProvince: '', postalCode: '' })
      setDraftId(d.id); setStep('review')
    }).catch(() => setError('That draft could not be loaded — it may have been sent or deleted.'))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Autosave (debounced) while reviewing.
  useEffect(() => {
    if (!draftId || step === 'search') return
    if (saveTimer.current) window.clearTimeout(saveTimer.current)
    setDraftSaved('saving')
    saveTimer.current = window.setTimeout(async () => {
      try {
        const payload: DraftPayload = { form: draftForm(form), re14, agency, forms: [forms.re21 && 're_21', forms.re14 && 're_14', forms.agency && 'agency_disclosure'].filter(Boolean) as string[], listing: listing ? { mlsNumber: listing.mlsNumber, address: listing.unparsedAddress, listAgentEmail: listing.listAgentEmail, listAgentName: listing.listAgentFullName } : null, source: 'mls' }
        await api.saveDraft({ id: draftId, title: String(form.propertyAddress || listing?.unparsedAddress || 'Untitled'), source: 'mls', payload })
        setDraftSaved('saved')
      } catch { setDraftSaved('error') }
    }, 1200)
    return () => { if (saveTimer.current) window.clearTimeout(saveTimer.current) }
  }, [form, re14, agency, forms, draftId, step]) // eslint-disable-line react-hooks/exhaustive-deps

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
    // Saved defaults first (team wins, then the agent's own), then the MLS, then presets.
    const f = applyLoanTypePresets(prefillFromListing(applyDefaults(defaultRE21(), savedDefaults.effective), l))
    setForm(f)
    const eff = savedDefaults.effective as Record<string, string>
    setRe14((r) => ({ ...r, searchCity: l.city, searchCounty: l.countyOrParish || '', searchState: l.stateOrProvince || 'Idaho',
      cancellationPercentage: eff.cancellationPercentage || r.cancellationPercentage, compensationFlatFee: eff.compensationFlatFee || r.compensationFlatFee,
      compensationPercentage: eff.compensationPercentage || r.compensationPercentage, agencyType: eff.agencyType || r.agencyType, propertyType: eff.propertyType || r.propertyType }))
    if (!draftId) setDraftId(crypto.randomUUID())
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
      const r = await api.sendPacket(buildPacket(form, re14, agency, forms, { email: listing?.listAgentEmail, name: listing?.listAgentFullName }, draftId || undefined))
      navigate(`/deals/${r.deal_id}`)
    } catch (err) { setError(String(err)) } finally { setBusy(null) }
  }

  const selectedCount = Object.values(forms).filter(Boolean).length

  const stepper = (
    <div className="stepper">
      {(['search', 'review', 'preview'] as const).map((k, i) => { const order = ['search', 'review', 'preview']; const cur = order.indexOf(step); return (
        <span key={k} style={{ display: 'contents' }}>
          {i > 0 && <span className="sep" />}
          <span className={`step ${step === k ? 'active' : i < cur ? 'done' : ''}`}><i>{i < cur ? '✓' : i + 1}</i>{k === 'search' ? 'Find the property' : k === 'review' ? 'Review the packet' : 'Preview & send'}</span>
        </span>
      )})}
    </div>
  )

  // ---------------- render ----------------
  if (step === 'search') return (
    <>
      {stepper}
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
      {stepper}
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
      {stepper}
      <div className="pagehead">
        <div><h1>Review Packet</h1><p className="muted">{listing?.unparsedAddress} · MLS #{listing?.mlsNumber} · agent {me.first_name} {me.last_name}</p></div>
        <div className="filters">
          <span className={`muted small savestate ${draftSaved}`}>{draftSaved === 'saving' ? 'Saving…' : draftSaved === 'saved' ? '✓ Draft saved — resume on any device' : draftSaved === 'error' ? 'Draft not saved (offline?)' : ''}</span>
          {draftId && <button className="link danger" onClick={async () => { if (!confirm('Discard this draft?')) return; try { await api.deleteDraft(draftId) } catch { /* gone */ } navigate('/') }}>Discard draft</button>}
          <button className="link" onClick={() => setStep('search')}>← Different property</button>
        </div>
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
            {isOpen && <FieldGrid fields={s.fields} values={form} onChange={set} showMissing={showMissing} locked={savedDefaults.locked} />}
          </section>
        )
      })}
      {tab === 're14' && (
        <section className="card section"><p className="muted small">Buyer Representation Agreement. Buyers, agent and property come from the RE-21; these are only what the RE-14 adds.</p>
          <FieldGrid fields={RE14_FIELDS} values={re14} onChange={(k, v) => setRe14((r) => ({ ...r, [k]: String(v ?? '') }))} showMissing={false} locked={savedDefaults.locked} /></section>
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

export function FieldGrid({ fields, values, onChange, showMissing, locked = [] }: { fields: Field[]; values: Record<string, unknown>; onChange: (k: string, v: unknown) => void; showMissing: boolean; locked?: string[] }) {
  const groups: { name: string | undefined; fields: Field[] }[] = []
  for (const f of fields) { const g = groups[groups.length - 1]; if (g && g.name === f.group) g.fields.push(f); else groups.push({ name: f.group, fields: [f] }) }
  return (
    <>
      {groups.map((g, i) => (
        <div key={i} className={g.name ? 'fgroup' : 'fplain'}>
          {g.name && <div className="fgname">{g.name}</div>}
          <div className="fgrid">{g.fields.map((f) => <FieldInput key={f.key} f={f} value={values[f.key]} onChange={(v) => onChange(f.key, v)} invalid={showMissing && !!f.required && (values[f.key] === undefined || values[f.key] === null || values[f.key] === '')} locked={locked.includes(f.key)} />)}</div>
        </div>
      ))}
    </>
  )
}

export function FieldInput({ f, value, onChange, invalid, locked = false }: { f: Field; value: unknown; onChange: (v: unknown) => void; invalid: boolean; locked?: boolean }) {
  const cls = invalid ? 'invalid' : ''
  const label = <>{f.label}{f.required && <span className="req"> *</span>}{locked && <span className="lock" title="Set by your team lead">🔒 team</span>}</>
  if (locked) return <label className={`lockedfield ${f.type === 'textarea' ? 'wide' : ''}`}>{label}<div className="lockedval">{f.type === 'toggle' ? (value ? 'Yes' : 'No') : f.type === 'select' || f.type === 'multiselect' ? String(value ?? '').split(',').map((v) => (f.options || []).find(([k]) => k === v.trim())?.[1] || v).join(', ') : String(value ?? '—')}</div></label>
  switch (f.type) {
    case 'multiselect': {
      const chosen = new Set(String(value ?? '').split(',').map((v) => v.trim()).filter(Boolean))
      return (
        <label className="wide">{label}
          <div className="chips">{f.options!.map(([v, l]) => (
            <button type="button" key={v} className={`chip ${chosen.has(v) ? 'on' : ''}`} onClick={() => { chosen.has(v) ? chosen.delete(v) : chosen.add(v); onChange(Array.from(chosen).join(',')) }}>{chosen.has(v) ? '✓ ' : ''}{l}</button>
          ))}</div>
        </label>
      )
    }
    case 'tags': return <TagsInput label={label} value={String(value ?? '')} onChange={(v) => onChange(v)} />
    case 'toggle': return <label className="check ftoggle"><input type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} /><span>{f.label}</span></label>
    case 'select': return <label>{label}<select className={cls} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)}><option value="">—</option>{f.options!.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
    case 'textarea': return <label className="wide">{label}<textarea className={cls} rows={3} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} /></label>
    case 'money': return <label>{label}<input className={cls} inputMode="decimal" value={value === undefined || value === null ? '' : String(value)} placeholder="$" onChange={(e) => { const n = e.target.value.replace(/[^0-9.]/g, ''); onChange(n === '' ? null : Number(n)) }} /></label>
    case 'int': return <label>{label}<input className={cls} inputMode="numeric" value={value === undefined || value === null ? '' : String(value)} onChange={(e) => { const n = e.target.value.replace(/[^0-9]/g, ''); onChange(n === '' ? null : Number(n)) }} /></label>
    case 'date': return <label>{label}<input className={cls} type="date" value={typeof value === 'string' ? value.slice(0, 10) : ''} onChange={(e) => onChange(e.target.value || null)} /></label>
    default: return <label>{label}<input className={cls} type={f.type === 'email' ? 'email' : f.type === 'phone' ? 'tel' : 'text'} value={String(value ?? '')} onChange={(e) => onChange(e.target.value || null)} /></label>
  }
}


/** Comma-joined list editor: type, Enter/comma adds a chip; click a chip to remove it. */
function TagsInput({ label, value, onChange }: { label: React.ReactNode; value: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState('')
  const items = value.split(',').map((v) => v.trim()).filter(Boolean)
  const commit = () => { const t = draft.trim().replace(/,$/, ''); if (t && !items.includes(t)) onChange([...items, t].join(', ')); setDraft('') }
  return (
    <label className="wide">{label}
      <div className="tagbox" onClick={(e) => (e.currentTarget.querySelector('input') as HTMLInputElement | null)?.focus()}>
        {items.map((it) => <button type="button" key={it} className="chip on" onClick={() => onChange(items.filter((x) => x !== it).join(', '))}>{it} ×</button>)}
        <input value={draft} placeholder={items.length ? 'add another…' : 'type and press Enter'} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); commit() } else if (e.key === 'Backspace' && !draft && items.length) onChange(items.slice(0, -1).join(', ')) }}
          onBlur={commit} />
      </div>
    </label>
  )
}
