import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Deal, type Me } from '../api'
import { computeDeadlines, urgency } from '../deadlines'

const STATUS_CLASS: Record<string, string> = { fully_executed: 'ok', out_for_signature: 'warn', cancelled: 'bad' }

function nextDeadline(d: Deal) {
  const upcoming = computeDeadlines(d).filter((x) => urgency(x.date) !== 'overdue')
  return upcoming[0] || null
}

export default function Pipeline({ me }: { me: Me }) {
  const [deals, setDeals] = useState<Deal[] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [groupByAgent, setGroupByAgent] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const teamView = me.role !== 'agent'

  const load = () => api.deals().then(setDeals).catch((e) => setError(String(e)))
  useEffect(() => { load() }, [])

  const groups = useMemo(() => {
    if (!deals) return []
    const visible = deals.filter((d) => showArchived ? d.is_archived : !d.is_archived)
    if (!teamView || !groupByAgent) return [{ agent: null as string | null, deals: visible }]
    const byAgent = new Map<string, Deal[]>()
    visible.forEach((d) => { const k = me.is_superuser && d.agent_team ? `${d.agent_name} · ${d.agent_team}` : d.agent_name; byAgent.set(k, [...(byAgent.get(k) || []), d]) })
    return Array.from(byAgent.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([agent, deals]) => ({ agent, deals }))
  }, [deals, showArchived, groupByAgent, teamView, me.is_superuser])

  if (error) return <p className="error">{error}</p>
  if (!deals) return <p className="muted">Loading pipeline…</p>

  return (
    <>
      <div className="pagehead">
        <h1>{me.is_superuser ? 'All Deals' : teamView ? 'Team Pipeline' : 'My Pipeline'}</h1>
        <div className="filters">
          {(me.role === 'agent' || me.is_superuser) && <Link to="/new" className="primary btnlink">+ Start from property</Link>}
          {teamView && <label className="toggle"><input type="checkbox" checked={groupByAgent} onChange={(e) => setGroupByAgent(e.target.checked)} /> Group by agent</label>}
          <label className="toggle"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived</label>
        </div>
      </div>
      {groups.every((g) => g.deals.length === 0) && <p className="muted">{showArchived ? 'No archived deals.' : 'No active deals yet.'}</p>}
      {groups.map((g) => (
        <div key={g.agent ?? 'all'} className="group">
          {g.agent && <h2 className="grouphead">{g.agent} <span className="muted">· {g.deals.length} deal{g.deals.length === 1 ? '' : 's'}</span></h2>}
          <table className="table">
            <thead><tr><th>Property</th><th>Buyer(s)</th>{teamView && !groupByAgent && <th>Agent</th>}<th>Status</th><th>Packet</th><th>Next deadline</th><th></th></tr></thead>
            <tbody>
              {g.deals.map((d) => {
                const nd = nextDeadline(d)
                return (
                  <tr key={d.id}>
                    <td><Link to={`/deals/${d.id}`}><b>{d.property_address}</b></Link></td>
                    <td>{d.buyer_names}</td>
                    {teamView && !groupByAgent && <td>{d.agent_name}</td>}
                    <td><span className={`status ${STATUS_CLASS[d.status] || ''}`}>{d.status_display}</span></td>
                    <td>{d.signed_pdf_url ? <a className="docbtn" href={d.signed_pdf_url} target="_blank" rel="noreferrer">Executed packet</a> : d.draft_pdf_url ? <a className="docbtn" href={d.draft_pdf_url} target="_blank" rel="noreferrer">Offer packet</a> : <span className="muted">—</span>}</td>
                    <td>{nd ? <><span className={`status ${urgency(nd.date) === 'soon' ? 'warn' : ''}`}>{nd.date.toLocaleDateString()}</span> <span className="muted small">{nd.title}</span></> : <span className="muted">—</span>}</td>
                    <td className="right"><button className="link" onClick={() => api.setArchived(d.id, !d.is_archived).then(load)}>{d.is_archived ? 'Restore' : 'Archive'}</button></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ))}
    </>
  )
}
