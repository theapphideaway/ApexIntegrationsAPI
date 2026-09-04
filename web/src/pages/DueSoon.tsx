import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Deal, type Me } from '../api'
import { computeDeadlines, urgency, type Deadline } from '../deadlines'

type Row = Deadline & { deal: Deal; u: 'overdue' | 'soon' | 'later' }

export default function DueSoon({ me }: { me: Me }) {
  const [deals, setDeals] = useState<Deal[] | null>(null)
  const [agent, setAgent] = useState<string>('all')
  const [horizon, setHorizon] = useState<number>(14)
  const [includeTests, setIncludeTests] = useState(false)
  useEffect(() => { api.deals().then(setDeals) }, [])

  const rows = useMemo<Row[]>(() => {
    if (!deals) return []
    const limit = Date.now() + horizon * 86400_000
    return deals
      .filter((d) => !d.is_archived && d.status !== 'cancelled' && (includeTests || !d.is_test) && (agent === 'all' || d.agent_id === agent))
      .flatMap((d) => computeDeadlines(d).map((x) => ({ ...x, deal: d, u: urgency(x.date) })))
      .filter((r) => r.date.getTime() <= limit)
      .sort((a, b) => a.date.getTime() - b.date.getTime())
  }, [deals, agent, horizon, includeTests])

  if (!deals) return <p className="muted">Loading…</p>
  const agents = Array.from(new Map(deals.map((d) => [d.agent_id, d.agent_name])).entries())
  const noTimeline = deals.filter((d) => !d.is_archived && computeDeadlines(d).length === 0).length

  // Group by calendar day for an agenda view.
  const days: { key: string; date: Date; u: Row['u']; rows: Row[] }[] = []
  for (const r of rows) {
    const key = r.date.toDateString()
    let day = days.find((d) => d.key === key)
    if (!day) { day = { key, date: r.date, u: r.u, rows: [] }; days.push(day) }
    day.rows.push(r)
  }
  const overdue = rows.filter((r) => r.u === 'overdue').length
  const soon = rows.filter((r) => r.u === 'soon').length

  return (
    <>
      <div className="pagehead">
        <div><h1>Due Soon</h1><p className="sub">{rows.length} deadline{rows.length === 1 ? '' : 's'} in the next {horizon === 365 ? 'year' : `${horizon} days`}{overdue ? ` · ${overdue} overdue` : ''}{soon ? ` · ${soon} within 3 days` : ''}</p></div>
        <div className="filters">
          {me.role !== 'agent' && (
            <select value={agent} onChange={(e) => setAgent(e.target.value)}>
              <option value="all">All agents</option>
              {agents.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          )}
          {me.is_superuser && <label className="toggle"><input type="checkbox" checked={includeTests} onChange={(e) => setIncludeTests(e.target.checked)} /> Include test deals</label>}
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            <option value={7}>Next 7 days</option><option value={14}>Next 14 days</option><option value={30}>Next 30 days</option><option value={365}>Everything</option>
          </select>
        </div>
      </div>
      {rows.length === 0 && <div className="empty"><b>Nothing due in this window</b><span>Widen the window or check back after the next contract executes.</span></div>}
      <div className="agenda">
        {days.map((day) => (
          <div className={`day ${day.u}`} key={day.key}>
            <div className="date">{day.date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}<small>{day.u === 'overdue' ? 'Overdue' : day.u === 'soon' ? 'Soon' : ''}</small></div>
            <div className="items">
              {day.rows.map((r, i) => (
                <div className={`item ${r.u}`} key={i}>
                  <div><div className="t">{r.title}</div><div className="m"><Link to={`/deals/${r.deal.id}`}>{r.deal.property_address}</Link> · {r.deal.buyer_names}{me.role !== 'agent' ? ` · ${r.deal.agent_name}` : ''}</div></div>
                  <span className="muted small">{r.note}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      {noTimeline > 0 && <p className="muted small" style={{ marginTop: 16 }}>{noTimeline} active deal{noTimeline === 1 ? ' has' : 's have'} no timeline yet — deadlines appear once a deal is executed and has its contract terms on file.</p>}
    </>
  )
}
