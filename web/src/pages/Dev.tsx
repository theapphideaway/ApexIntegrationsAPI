import { useEffect, useState } from 'react'
import { api, type DevSettings, type Team, type PortalUser, type Me, type ConnectStatus, type AccountSettingsCompare } from '../api'
import { Link, useLocation } from 'react-router-dom'
import ApiExplorer from './ApiExplorer'

const ROLES = [['agent', 'Agent'], ['tc', 'Transaction Coordinator'], ['admin', 'Team Admin']] as const

export default function Dev({ me }: { me: Me }) {
  const location = useLocation()
  const tab = location.pathname.endsWith('/api') ? 'api' : 'overview'
  return (
    <>
      <div className="pagehead"><div><h1>Developer Portal</h1><p className="sub">{me.email}</p></div></div>
      <div className="tabs">
        <Link className={`tab ${tab === 'overview' ? 'active' : ''}`} to="/dev">Overview</Link>
        <Link className={`tab ${tab === 'api' ? 'active' : ''}`} to="/dev/api">API Explorer</Link>
      </div>
      {tab === 'api' ? <ApiExplorer me={me} /> : <DevOverview me={me} />}
    </>
  )
}

function DevOverview({ me }: { me: Me }) {
  const [cfg, setCfg] = useState<DevSettings | null>(null)
  const [teams, setTeams] = useState<Team[]>([])
  const [users, setUsers] = useState<PortalUser[]>([])
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [newTeam, setNewTeam] = useState('')
  const [newUser, setNewUser] = useState({ email: '', first_name: '', last_name: '', phone_number: '', role: 'agent', organization: '' })
  const [rawKey, setRawKey] = useState(''); const [rawVal, setRawVal] = useState('')

  const reload = () => Promise.all([api.dev.settings(), api.dev.teams(), api.dev.users()])
    .then(([c, t, u]) => { setCfg(c); setTeams(t); setUsers(u); if (!newUser.organization && t[0]) setNewUser((n) => ({ ...n, organization: t[0].id })) })
    .catch((e) => setError(String(e)))
  useEffect(() => { reload() }, [])

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setError(null)
    try { await fn(); await reload() } catch (e) { setError(String(e)) } finally { setBusy(null) }
  }

  if (!cfg) return error ? <p className="error">{error}</p> : <p className="muted">Loading…</p>
  const ds = cfg.docusign

  return (
    <>
      <p className="muted small" style={{ marginBottom: 12 }}>DB: {cfg.server.db_engine} · DEBUG {String(cfg.server.debug)}</p>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice">{notice}</p>}

      <section className="card" style={{ marginBottom: 20 }}>
        <div className="cardhead"><h2>DocuSign environments</h2><span className={`status ${ds.master_production ? 'bad' : 'warn'}`}>MASTER: {ds.master_production ? 'PRODUCTION ENABLED' : 'TEST ONLY'}</span></div>
        <div className="master">
          <label className="check">
            <input type="checkbox" checked={ds.master_production} disabled={busy !== null || (!ds.master_production && !ds.environments.production.configured)}
              onChange={(e) => { if (e.target.checked && !confirm('Enable PRODUCTION DocuSign for users flagged Prod? Their envelopes become legally binding and billed.')) return; run('env', () => api.dev.patchSettings({ docusign_env: e.target.checked ? 'production' : 'demo' })) }} />
            <span><b>Production master switch</b> — {ds.production_users} user{ds.production_users === 1 ? '' : 's'} flagged for Prod below. Off = everyone uses the test account regardless of their flag.{!ds.environments.production.configured && ' (Disabled until production credentials are on the server.)'}</span>
          </label>
        </div>
        <div className="envgrid">
          {(['demo', 'production'] as const).map((env) => { const e = ds.environments[env]; return (
            <div key={env} className={`envcard ${(env === 'production') === ds.master_production ? 'active' : ''}`}>
              <b>{env === 'demo' ? 'Test (sandbox)' : 'Production'} {e.configured ? <span className="status ok">configured</span> : <span className="status bad">not configured</span>}</b>
              <div className="small muted">{e.auth_server}<br />{e.base_path}</div>
              <ul className="checks">
                <li className={e.client_id_set ? 'ok' : 'bad'}>Integration key {env === 'production' ? '(DOCUSIGN_PROD_CLIENT_ID)' : '(DOCUSIGN_CLIENT_ID)'}</li>
                <li className={e.user_id_set ? 'ok' : 'bad'}>Impersonated user ID</li>
                <li className={e.account_id_set ? 'ok' : 'bad'}>Account ID</li>
                <li className={e.private_key_present ? 'ok' : 'bad'}>RSA key · {e.private_key_path}</li>
              </ul>
              <div className="row">
                <button className="link" disabled={!e.configured || busy !== null} onClick={async () => { setBusy('test'); setTestResult(null); try { setTestResult(JSON.stringify(await api.dev.testDocuSign(env), null, 2)) } catch (err) { setTestResult(String(err)) } finally { setBusy(null) } }}>Test connection</button>
                {e.consent_url && <a className="link" href={e.consent_url} target="_blank" rel="noreferrer" title="One-time JWT consent: sign in as the API user and click Allow">Grant consent ↗</a>}
              </div>
            </div>
          )})}
        </div>
        {testResult && <pre className="result">{testResult}</pre>}
        <p className="muted small">Secrets live only in the server .env. Production needs its own integration key, consent, RSA key (private_key_prod.pem) and account ID; the base URL is resolved automatically unless DOCUSIGN_PROD_BASE_PATH is set.</p>
      </section>

      <Cutover ds={ds} busy={busy} setBusy={setBusy} setError={setError} />

      <div className="grid">
        <section className="card">
          <div className="cardhead"><h2>Teams</h2></div>
          <table className="table compact">
            <thead><tr><th>Name</th><th>Plan</th><th>Members</th><th>Deals</th><th>Active</th></tr></thead>
            <tbody>{teams.map((t) => (
              <tr key={t.id}>
                <td><input className="inline" defaultValue={t.name} onBlur={(e) => e.target.value !== t.name && run('team', () => api.dev.patchTeam(t.id, { name: e.target.value }))} /></td>
                <td><select className="inline" value={t.plan_type} onChange={(e) => run('team', () => api.dev.patchTeam(t.id, { plan_type: e.target.value }))}><option value="basic">Basic</option><option value="pro">Pro</option><option value="enterprise">Enterprise</option></select></td>
                <td>{t.member_count}</td><td>{t.deal_count}</td>
                <td><input type="checkbox" checked={t.is_active} onChange={(e) => run('team', () => api.dev.patchTeam(t.id, { is_active: e.target.checked }))} /></td>
              </tr>))}</tbody>
          </table>
          <form className="row" onSubmit={(e) => { e.preventDefault(); run('newteam', () => api.dev.createTeam({ name: newTeam.trim() })).then(() => setNewTeam('')) }}>
            <input placeholder="New team name" value={newTeam} onChange={(e) => setNewTeam(e.target.value)} required />
            <button className="primary" disabled={busy !== null}>Add team</button>
          </form>
        </section>

        <section className="card">
          <div className="cardhead"><h2>Raw settings</h2></div>
          <pre className="result">{JSON.stringify(cfg.settings, null, 2)}</pre>
          <form className="row" onSubmit={(e) => { e.preventDefault(); let v: unknown = rawVal; try { v = JSON.parse(rawVal) } catch { /* string */ } run('raw', () => api.dev.patchSettings({ [rawKey.trim()]: v })).then(() => { setRawKey(''); setRawVal('') }) }}>
            <input placeholder="key" value={rawKey} onChange={(e) => setRawKey(e.target.value)} required />
            <input placeholder='value (JSON or text)' value={rawVal} onChange={(e) => setRawVal(e.target.value)} required />
            <button className="primary" disabled={busy !== null}>Set</button>
          </form>
        </section>
      </div>

      <section className="card" style={{ marginTop: 20 }}>
        <div className="cardhead"><h2>Users</h2><span className="muted small">{users.length} total</span></div>
        <table className="table compact">
          <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Team</th><th>Deals</th><th>DocuSign</th><th>FUB</th><th>Active</th><th></th></tr></thead>
          <tbody>{users.map((u) => (
            <tr key={u.id} className={u.is_active ? '' : 'inactive'}>
              <td>{u.first_name} {u.last_name}{u.is_superuser && <span className="pill" style={{ marginLeft: 6 }}>dev</span>}</td>
              <td>{u.email}</td>
              <td><input className="inline" defaultValue={u.phone_number || ''} placeholder="—" onBlur={(e) => (e.target.value || null) !== u.phone_number && run('user', () => api.dev.patchUser(u.id, { phone_number: e.target.value }))} /></td>
              <td><select className="inline" value={u.role} onChange={(e) => run('user', () => api.dev.patchUser(u.id, { role: e.target.value }))}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></td>
              <td><select className="inline" value={u.organization || ''} onChange={(e) => run('user', () => api.dev.patchUser(u.id, { organization: e.target.value || null }))}><option value="">— none —</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></td>
              <td>{u.deal_count}</td>
              <td>
                <button type="button" className={`envtoggle ${u.docusign_production ? 'prod' : 'test'}`} disabled={busy !== null} title="Click to switch this user's DocuSign account"
                  onClick={() => run('user', () => api.dev.patchUser(u.id, { docusign_production: !u.docusign_production }))}>
                  {u.docusign_production ? 'PROD' : 'TEST'}
                </button>
                {u.docusign_production && u.docusign_env !== 'production' && <span className="muted small" title="Flagged for production but the master switch is off or prod isn't configured — still sending on test."> → test</span>}
              </td>
              <td>{u.fub_connected ? <><span className="status ok">linked</span> <button className="link small" disabled={busy !== null} title={`Register inbound webhooks on FUB account ${u.fub_account_id || '?'}`} onClick={async () => { setBusy('fub'); try { const r = await api.fubRegisterWebhooks(u.id); setTestResult(JSON.stringify(r, null, 2)) } catch (e) { setError(String(e)) } finally { setBusy(null) } }}>listeners</button></> : <span className="muted">—</span>}</td>
              <td><input type="checkbox" checked={u.is_active} disabled={u.id === me.id} onChange={(e) => run('user', () => api.dev.patchUser(u.id, { is_active: e.target.checked }))} /></td>
              <td className="right">{u.id !== me.id && <button className="link danger" onClick={() => { if (!confirm(`Delete ${u.email}?`)) return; run('del', async () => { try { await api.dev.deleteUser(u.id) } catch (err) { if (String(err).includes('owns') && confirm(`${err}\n\nDelete the user AND their deals?`)) await api.dev.deleteUser(u.id, true); else throw err } }) }}>Delete</button>}</td>
            </tr>))}</tbody>
        </table>
        <form className="row wrap" onSubmit={(e) => { e.preventDefault(); run('newuser', () => api.dev.createUser(newUser)).then(() => setNewUser((n) => ({ ...n, email: '', first_name: '', last_name: '', phone_number: '' }))) }}>
          <input placeholder="Email" type="email" required value={newUser.email} onChange={(e) => setNewUser({ ...newUser, email: e.target.value })} />
          <input placeholder="First" required value={newUser.first_name} onChange={(e) => setNewUser({ ...newUser, first_name: e.target.value })} />
          <input placeholder="Last" required value={newUser.last_name} onChange={(e) => setNewUser({ ...newUser, last_name: e.target.value })} />
          <input placeholder="Phone (optional)" value={newUser.phone_number} onChange={(e) => setNewUser({ ...newUser, phone_number: e.target.value })} />
          <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select required value={newUser.organization} onChange={(e) => setNewUser({ ...newUser, organization: e.target.value })}><option value="">Team…</option>{teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
          <button className="primary" disabled={busy !== null}>Add user</button>
        </form>
      </section>
    </>
  )
}


function Cutover({ ds, busy, setBusy, setError }: { ds: DevSettings['docusign']; busy: string | null; setBusy: (b: string | null) => void; setError: (e: string | null) => void }) {
  const [connect, setConnect] = useState<ConnectStatus | null>(null)
  const [acct, setAcct] = useState<AccountSettingsCompare | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const prod = ds.environments.production
  const mine = connect?.configurations.filter((c) => c.is_ours) ?? []

  async function go(label: string, fn: () => Promise<void>) {
    setBusy(label); setError(null); setMsg(null)
    try { await fn() } catch (e) { const err = e as { body?: { consent_url?: string }; message?: string }; setError(String(err?.message ?? e)); if (err?.body?.consent_url) setMsg(`Consent required — open: ${err.body.consent_url}`) } finally { setBusy(null) }
  }
  const val = (env: string, k: string) => { const e = acct?.environments[env]; return e && !('error' in e) ? String(e[k] ?? '—') : (e && 'error' in e ? '⚠ ' + e.error : '—') }

  return (
    <section className="card" style={{ marginBottom: 20 }}>
      <div className="cardhead"><h2>Production cutover</h2>{prod.configured ? <span className="status ok">credentials on server</span> : <span className="status warn">waiting on credentials</span>}</div>
      {msg && <p className="notice">{msg}</p>}
      <ol className="steps">
        <li><b>Credentials.</b> DOCUSIGN_PROD_CLIENT_ID / USER_ID / ACCOUNT_ID + private_key_prod.pem in the server .env, then reload. {prod.configured ? '✓' : '(not yet)'}</li>
        <li><b>Consent.</b> Once, signed in to DocuSign as the API user: {prod.consent_url ? <a href={prod.consent_url} target="_blank" rel="noreferrer">grant consent ↗</a> : <span className="muted">needs the client id first</span>}. The redirect URI must be listed on the integration key.</li>
        <li><b>Test connection</b> on the Production card above. It should name the API user and show the account id as a match.</li>
        <li><b>Signing settings.</b> Date/time stamps must match demo (M/d/yyyy, h:mm AM/PM, account timezone override, attach completed envelope). The account time zone itself (Mountain) is set once in DocuSign Admin → Regional Settings.
          <div className="row">
            <button className="link" disabled={busy !== null} onClick={() => go('acct', async () => setAcct(await api.dev.accountSettings()))}>Compare</button>
            <button className="link" disabled={busy !== null || !prod.configured} onClick={() => { if (!confirm('Copy the signing settings from demo onto the PRODUCTION account?')) return; go('acct-sync', async () => { await api.dev.syncAccountSettings('demo', 'production'); setAcct(await api.dev.accountSettings()) }) }}>Copy demo → production</button>
            {acct && <span className={`status ${acct.in_sync ? 'ok' : 'warn'}`}>{acct.in_sync ? 'in sync' : 'differs'}</span>}
          </div>
          {acct && <table className="table compact"><thead><tr><th>Setting</th><th>Demo</th><th>Production</th></tr></thead>
            <tbody>{acct.keys.map((k) => <tr key={k}><td className="small">{k}</td><td className="small">{val('demo', k)}</td><td className="small">{val('production', k)}</td></tr>)}</tbody></table>}
        </li>
        <li><b>Connect webhook</b> → <code>{ds.webhook_url}</code> (envelope-completed, JSON, PDFs included, HMAC on). HMAC verification on the server: {ds.hmac_configured ? <span className="status ok">on</span> : <span className="status warn">off — set DOCUSIGN_CONNECT_HMAC_KEYS</span>}
          <div className="row">
            {(['demo', 'production'] as const).map((env) => <button key={env} className="link" disabled={busy !== null || !ds.environments[env].configured} onClick={() => go('connect', async () => setConnect(await api.dev.connectStatus(env)))}>Check {env}</button>)}
            {connect && mine.length === 0 && <button className="link" disabled={busy !== null} onClick={() => { if (!confirm(`Create the Docuflow webhook on the ${connect.env} DocuSign account?`)) return; go('connect-create', async () => { await api.dev.ensureConnect(connect.env); setConnect(await api.dev.connectStatus(connect.env)) }) }}>Create webhook on {connect.env}</button>}
          </div>
          {connect && <div className="small">
            {connect.configurations.length === 0 && <p className="muted">No Connect configurations on {connect.env}. If “Create” fails, Connect isn’t enabled on the plan — ask DocuSign support to enable it.</p>}
            {connect.configurations.map((c) => <div key={c.connect_id} className="muted" style={{ marginTop: 4 }}>
              {c.is_ours ? '✓' : '·'} <b>{c.name}</b> #{c.connect_id} → {c.url} · events {c.events.join(', ') || '—'} · documents {c.include_documents} · HMAC {c.include_hmac} · all users {c.all_users}
              {c.is_ours && c.include_hmac !== 'true' && <span className="status warn" style={{ marginLeft: 6 }}>HMAC off in DocuSign</span>}
            </div>)}
          </div>}
        </li>
        <li><b>Pilot.</b> Flag one user PROD in Users below, send one real packet, confirm it lands as fully executed, then flip the master switch.</li>
        <li><b>Go-live.</b> Promote the integration key in DocuSign Apps &amp; Keys once the pilot envelope has completed.</li>
      </ol>
    </section>
  )
}
