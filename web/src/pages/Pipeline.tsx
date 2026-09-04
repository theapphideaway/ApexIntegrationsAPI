import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Deal, type Me, type Draft } from '../api'
import { computeDeadlines, urgency } from '../deadlines'
import { initials } from '../App'

const STATUS_CLASS: Record<string, string> = { fully_executed: 'ok', out_for_signature: 'warn', cancelled: 'bad' }

function nextDeadline(d: Deal) {
  const upcoming = computeDeadlines(d).filter((x) => urgency(x.date) !== 'overdue')
  return upcoming[0] || null
}

export default function Pipeline({ me }: { me: Me }) {
  const [deals, setDeals] = useState<Deal[] | null>(null)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [showArchived, setShowArchived] = useState(false)
  const [groupByAgent, setGroupByAgent] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const teamView = me.role !== 'agent'

  const load = () => { api.drafts().then(setDrafts).catch(() => {}); return api.deals().then(setDeals).catch((e) => setError(String(e))) }
  useEffect(() => { load() }, [])

  const groups = useMemo(() => {
    if (!deals) return []
    const visible = deals.filter((d) => (showArchived ? d.is_archived : !d.is_archived))
    if (!teamView || !groupByAgent) return [{ agent: null as string | null, deals: visible }]
    const byAgent = new Map<string, Deal[]>()
    visible.forEach((d) => { const k = me.is_superuser && d.agent_team ? `${d.agent_name} · ${d.agent_team}` : d.agent_name; byAgent.set(k, [...(byAgent.get(k) || []), d]) })
    return Array.from(byAgent.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([agent, deals]) => ({ agent, deals }))
  }, [deals, showArchived, groupByAgent, teamView, me.is_superuser])

  if (error) return <p className="error">{error}</p>
  if (!deals) return <div className="deals">{[0, 1, 2].map((i) => <div className="dealrow" key={i}><div className="skeleton" style={{ width: '60%' }} /><div className="skeleton" style={{ width: '40%' }} /><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /><div /></div>)}</div>

  const active = deals.filter((d) => !d.is_archived)
  const awaiting = active.filter((d) => d.status === 'out_for_signature').length
  const executed = active.filter((d) => d.status === 'fully_executed').length
  const soon = active.flatMap(computeDeadlines).filter((x) => urgency(x.date) === 'soon').length
  const overdue = active.flatMap(computeDeadlines).filter((x) => urgency(x.date) === 'overdue').length

  return (
    <>
      <div className="pagehead">
        <div>
          <h1>{me.is_superuser ? 'All Deals' : teamView ? 'Team Pipeline' : 'My Pipeline'}</h1>
          <p className="sub">{active.length} active deal{active.length === 1 ? '' : 's'}{teamView ? ' across the team' : ''}</p>
        </div>
        <div className="filters">
          {teamView && <label className="toggle"><input type="checkbox" checked={groupByAgent} onChange={(e) => setGroupByAgent(e.target.checked)} /> Group by agent</label>}
          <label className="toggle"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Archived</label>
          {(me.role === 'agent' || me.is_superuser) && <Link to="/new" className="btnlink">+ Start from property</Link>}
        </div>
      </div>

      {!showArchived && (
        <div className="stats">
          <div className="stat"><div className="k">Active</div><div className="v">{active.length}</div></div>
          <div className="stat"><div className="k">Awaiting signature</div><div className="v">{awaiting}</div></div>
          <div className="stat"><div className="k">Under contract</div><div className="v">{executed}</div></div>
          <div className="stat"><div className="k">Due in 3 days</div><div className="v" style={{ color: soon ? 'var(--warn)' : undefined }}>{soon}</div></div>
          <div className="stat"><div className="k">Overdue</div><div className="v" style={{ color: overdue ? 'var(--bad)' : undefined }}>{overdue}</div></div>
        </div>
      )}

      {drafts.length > 0 && !showArchived && (
        <div className="group">
          <h2 className="grouphead">Drafts <span className="muted">· {drafts.length} unfinished packet{drafts.length === 1 ? '' : 's'}</span></h2>
          <div className="deals">
            {drafts.map((d) => (
              <div className="dealrow draft" key={d.id}>
                <div className="col"><Link to={`/new?draft=${d.id}`} className="addr">{d.title || 'Untitled packet'}</Link><div className="meta">{d.source === 'dictation' ? 'From dictation' : d.source === 'manual' ? 'Manual entry' : d.source === 'revision' ? 'Revision' : 'From MLS'}{teamView ? ` · ${d.agent_name}` : ''} · last edited on {d.device === 'ios' ? 'phone' : 'web'}</div></div>
                <div className="col"><div className="lbl">Status</div><span className="status warn">Draft</span></div>
                <div className="col" />
                <div className="col"><div className="lbl">Buyer</div><span className="muted">{String(d.payload?.form?.buyerName || '—')}</span></div>
                <div className="col"><div className="lbl">Updated</div><span className="muted">{new Date(d.updated_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span></div>
                <div className="col right"><Link to={`/new?draft=${d.id}`} className="docbtn" style={{ marginLeft: 0 }}>Resume</Link> <button className="link danger" onClick={async () => { if (!confirm('Delete this draft?')) return; await api.deleteDraft(d.id); load() }}>Delete</button></div>
              </div>
            ))}
          </div>
        </div>
      )}

      {groups.every((g) => g.deals.length === 0) && drafts.length === 0 && (
        <div className="empty"><b>{showArchived ? 'No archived deals' : 'No active deals yet'}</b>{!showArchived && (me.role === 'agent' || me.is_superuser) ? <span>Start one from an MLS listing and the packet is prefilled for you.</span> : <span>Deals appear here as agents send packets.</span>}</div>
      )}

      {groups.map((g) => (
        <div key={g.agent ?? 'all'} className="group">
          {g.agent && <h2 className="grouphead"><span className="avatar sm" style={{ background: 'var(--fill)', color: 'var(--fill-ink)', border: 0 }}>{initials(...(g.agent.split(' · ')[0].split(' ') as [string, string]))}</span>{g.agent} <span className="muted">· {g.deals.length} deal{g.deals.length === 1 ? '' : 's'}</span></h2>}
          <div className="deals">
            {g.deals.map((d) => {
              const nd = nextDeadline(d)
              const u = nd ? urgency(nd.date) : 'later'
              return (
                <div className="dealrow" key={d.id}>
                  <div className="col"><Link to={`/deals/${d.id}`} className="addr">{d.property_address}</Link><div className="meta">{d.buyer_names}{teamView && !groupByAgent ? ` · ${d.agent_name}` : ''}</div></div>
                  <div className="col"><div className="lbl">Status</div><span className={`status ${STATUS_CLASS[d.status] || ''}`}>{d.status_display}</span></div>
                  <div className="col"><div className="lbl">Packet</div>{d.signed_pdf_url ? <a className="docbtn" style={{ marginLeft: 0 }} href={d.signed_pdf_url} target="_blank" rel="noreferrer">Executed</a> : d.draft_pdf_url ? <a className="docbtn" style={{ marginLeft: 0 }} href={d.draft_pdf_url} target="_blank" rel="noreferrer">Offer</a> : <span className="muted">—</span>}</div>
                  <div className="col"><div className="lbl">Next deadline</div>{nd ? <><span className={`status ${u === 'soon' ? 'warn' : ''}`}>{nd.date.toLocaleDateString()}</span><div className="meta">{nd.title}</div></> : <span className="muted">—</span>}</div>
                  <div className="col"><div className="lbl">Updated</div><span className="muted">{new Date(d.updated_at).toLocaleDateString()}</span></div>
                  <div className="col right"><button className="link" onClick={() => api.setArchived(d.id, !d.is_archived).then(load)}>{d.is_archived ? 'Restore' : 'Archive'}</button></div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </>
  )
}
