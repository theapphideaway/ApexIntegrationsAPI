import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Deal, type Me } from '../api'

const STATUS_CLASS: Record<string, string> = { fully_executed: 'ok', out_for_signature: 'warn', cancelled: 'bad' }

export default function Pipeline({ me }: { me: Me }) {
  const [deals, setDeals] = useState<Deal[] | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const teamView = me.role !== 'agent'

  const load = () => api.deals().then(setDeals).catch((e) => setError(String(e)))
  useEffect(() => { load() }, [])

  if (error) return <p className="error">{error}</p>
  if (!deals) return <p className="muted">Loading pipeline…</p>

  const visible = deals.filter((d) => showArchived ? d.is_archived : !d.is_archived)

  return (
    <>
      <div className="pagehead">
        <h1>{teamView ? 'Team Pipeline' : 'My Pipeline'}</h1>
        <label className="toggle"><input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Show archived</label>
      </div>
      {visible.length === 0 && <p className="muted">{showArchived ? 'No archived deals.' : 'No active deals yet.'}</p>}
      <table className="table">
        <thead><tr><th>Property</th><th>Buyer(s)</th>{teamView && <th>Agent</th>}<th>Status</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          {visible.map((d) => (
            <tr key={d.id}>
              <td><Link to={`/deals/${d.id}`}><b>{d.property_address}</b></Link></td>
              <td>{d.buyer_names}</td>
              {teamView && <td>{d.agent_name}</td>}
              <td><span className={`status ${STATUS_CLASS[d.status] || ''}`}>{d.status_display}</span></td>
              <td className="muted">{new Date(d.updated_at).toLocaleDateString()}</td>
              <td className="right">
                <button className="link" onClick={() => api.setArchived(d.id, !d.is_archived).then(load)}>
                  {d.is_archived ? 'Restore' : 'Archive'}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}
