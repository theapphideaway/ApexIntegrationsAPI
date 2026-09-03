import { useEffect, useState } from 'react'
import { api, type Me, type PortalUser, type Team } from '../api'

const ROLES = [['agent', 'Agent'], ['tc', 'Transaction Coordinator'], ['admin', 'Team Admin']] as const
const ROLE_LABEL: Record<string, string> = Object.fromEntries(ROLES)

/** Team-admin portal: the admin's own team — members, roles, invitations. */
export default function TeamPage({ me }: { me: Me }) {
  const [team, setTeam] = useState<Team | null>(null)
  const [members, setMembers] = useState<PortalUser[]>([])
  const [dealCount, setDealCount] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [invite, setInvite] = useState({ email: '', first_name: '', last_name: '', phone_number: '', role: 'agent' })

  const load = () => api.team.get().then((r) => { setTeam(r.team); setMembers(r.members); setDealCount(r.deal_count) }).catch((e) => setError(String(e)))
  useEffect(() => { load() }, [])

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true); setError(null); setNotice(null)
    try { await fn(); await load(); if (done) setNotice(done) } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  if (error && !team) return <p className="error">{error}</p>
  if (!team) return <p className="muted">Loading your team…</p>

  const active = members.filter((m) => m.is_active)
  const byRole = (r: string) => active.filter((m) => m.role === r).length

  return (
    <>
      <div className="pagehead">
        <div>
          <h1><input className="inline title" defaultValue={team.name} onBlur={(e) => e.target.value.trim() && e.target.value !== team.name && run(() => api.team.rename(e.target.value.trim()), 'Team renamed')} /></h1>
          <p className="muted">{active.length} member{active.length === 1 ? '' : 's'} · {byRole('agent')} agent{byRole('agent') === 1 ? '' : 's'} · {byRole('tc')} TC · {byRole('admin')} admin · {dealCount} deal{dealCount === 1 ? '' : 's'}</p>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="cardhead"><h2>Members</h2></div>
        <table className="table compact">
          <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Deals</th><th>FUB</th><th>Active</th></tr></thead>
          <tbody>{members.map((u) => (
            <tr key={u.id} className={u.is_active ? '' : 'inactive'}>
              <td>{u.first_name} {u.last_name}{u.id === me.id && <span className="muted small"> (you)</span>}</td>
              <td>{u.email}</td>
              <td><input className="inline" defaultValue={u.phone_number || ''} placeholder="—" onBlur={(e) => (e.target.value || null) !== u.phone_number && run(() => api.team.patchMember(u.id, { phone_number: e.target.value }))} /></td>
              <td>
                {u.is_superuser ? <span className="muted">{ROLE_LABEL[u.role]}</span> : (
                  <select className="inline" value={u.role} disabled={busy} onChange={(e) => run(() => api.team.patchMember(u.id, { role: e.target.value }), `${u.first_name} is now ${ROLE_LABEL[e.target.value]}`)}>
                    {ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                )}
              </td>
              <td>{u.deal_count}</td>
              <td>{u.fub_connected ? <span className="status ok">linked</span> : <span className="muted">—</span>}</td>
              <td><input type="checkbox" checked={u.is_active} disabled={busy || u.id === me.id || u.is_superuser} onChange={(e) => { if (!e.target.checked && !confirm(`Deactivate ${u.email}? They won\'t be able to log in; their deals stay on the team.`)) return; run(() => api.team.patchMember(u.id, { is_active: e.target.checked })) }} /></td>
            </tr>))}</tbody>
        </table>
      </section>

      <section className="card">
        <div className="cardhead"><h2>Invite a member</h2><span className="muted small">They get an email with how to log in — no password, a one-time code each time.</span></div>
        <form className="row wrap" onSubmit={(e) => { e.preventDefault(); run(() => api.team.invite(invite), `Invitation sent to ${invite.email}`).then(() => setInvite({ email: '', first_name: '', last_name: '', phone_number: '', role: 'agent' })) }}>
          <input placeholder="Email" type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} />
          <input placeholder="First name" required value={invite.first_name} onChange={(e) => setInvite({ ...invite, first_name: e.target.value })} />
          <input placeholder="Last name" required value={invite.last_name} onChange={(e) => setInvite({ ...invite, last_name: e.target.value })} />
          <input placeholder="Phone (optional)" value={invite.phone_number} onChange={(e) => setInvite({ ...invite, phone_number: e.target.value })} />
          <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <button className="primary" disabled={busy}>Send invite</button>
        </form>
        <p className="muted small" style={{ marginTop: 10 }}><b>Roles:</b> Agents see their own deals. Transaction Coordinators see and work every deal on the team, and can send packets on an agent&apos;s behalf. Team Admins do everything a TC does and manage this page.</p>
      </section>
    </>
  )
}
