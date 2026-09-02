import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Deal, type Me } from '../api'
import { computeDeadlines, urgency, type Deadline } from '../deadlines'

type Row = Deadline & { deal: Deal; u: 'overdue' | 'soon' | 'later' }

export default function DueSoon({ me }: { me: Me }) {
  const [deals, setDeals] = useState<Deal[] | null>(null)
  const [agent, setAgent] = useState<string>('all')
  const [horizon, setHorizon] = useState<number>(14)
  useEffect(() => { api.deals().then(setDeals) }, [])

  const rows = useMemo<Row[]>(() => {
    if (!deals) return []
    const limit = Date.now() + horizon * 86400_000
    return deals
      .filter((d) => !d.is_archived && d.status !== 'cancelled' && (agent === 'all' || d.agent_id === agent))
      .flatMap((d) => computeDeadlines(d).map((x) => ({ ...x, deal: d, u: urgency(x.date) })))
      .filter((r) => r.date.getTime() <= limit)
      .sort((a, b) => a.date.getTime() - b.date.getTime())
  }, [deals, agent, horizon])

  if (!deals) return <p className="muted">Loading…</p>
  const agents = Array.from(new Map(deals.map((d) => [d.agent_id, d.agent_name])).entries())
  const noTimeline = deals.filter((d) => !d.is_archived && computeDeadlines(d).length === 0).length

  return (
    <>
      <div className="pagehead">
        <h1>Due Soon</h1>
        <div className="filters">
          {me.role !== 'agent' && (
            <select value={agent} onChange={(e) => setAgent(e.target.value)}>
              <option value="all">All agents</option>
              {agents.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          )}
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            <option value={7}>Next 7 days</option><option value={14}>Next 14 days</option><option value={30}>Next 30 days</option><option value={365}>Everything</option>
          </select>
        </div>
      </div>
      {rows.length === 0 && <p className="muted">Nothing due in this window.</p>}
      <table className="table">
        <thead><tr><th>When</th><th>Deadline</th><th>Deal</th>{me.role !== 'agent' && <th>Agent</th>}<th>Basis</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={r.u}>
              <td><span className={`status ${r.u === 'overdue' ? 'bad' : r.u === 'soon' ? 'warn' : ''}`}>{r.date.toLocaleDateString()}</span></td>
              <td><b>{r.title}</b></td>
              <td><Link to={`/deals/${r.deal.id}`}>{r.deal.property_address}</Link><div className="muted small">{r.deal.buyer_names}</div></td>
              {me.role !== 'agent' && <td>{r.deal.agent_name}</td>}
              <td className="muted">{r.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {noTimeline > 0 && <p className="muted small">{noTimeline} active deal(s) have no timeline yet — deadlines appear once a deal is executed and has its contract terms on file.</p>}
    </>
  )
}
