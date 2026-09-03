import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, NavLink, Link, useNavigate, useLocation } from 'react-router-dom'
import { api, auth, type Me } from './api'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import DealPage from './pages/Deal'
import DueSoon from './pages/DueSoon'
import Dev from './pages/Dev'
import NewDeal from './pages/NewDeal'
import TeamPage from './pages/Team'
import Console from './components/Console'
import { applyTheme, getTheme, type Theme } from './theme'

export const ROLE_LABEL: Record<Me['role'], string> = { admin: 'Team Admin', tc: 'Transaction Coordinator', agent: 'Agent' }
export const initials = (first?: string, last?: string, email?: string) => ((first?.[0] || '') + (last?.[0] || '') || (email?.[0] || '?')).toUpperCase()

const I = {
  pipeline: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/></svg>,
  due: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>,
  plus: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 5v14M5 12h14"/></svg>,
  team: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M15.5 20a5 5 0 0 1 6-4.5"/></svg>,
  dev: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 9l-4 3 4 3M16 9l4 3-4 3M13 5l-2 14"/></svg>,
  sun: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>,
  moon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>,
  console: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/></svg>,
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(auth.isLoggedIn)
  const [consoleOpen, setConsoleOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(getTheme())
  const toggleTheme = () => { const t: Theme = theme === 'dark' ? 'light' : 'dark'; setTheme(t); applyTheme(t) }
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    if (!auth.isLoggedIn) return
    api.me().then(setMe).catch(() => auth.clear()).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="center muted">Loading…</div>

  if (!auth.isLoggedIn || !me) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={(m) => { setMe(m); navigate('/') }} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  const canCreate = me.role === 'agent' || me.is_superuser
  const isAdmin = me.role === 'admin' || me.is_superuser
  const crumb = location.pathname.startsWith('/deals/') ? 'Deal' : location.pathname === '/due' ? 'Due Soon' : location.pathname === '/new' ? 'New Deal' : location.pathname === '/team' ? 'Team' : location.pathname === '/dev' ? 'Developer' : 'Pipeline'

  return (
    <div className="app">
      <aside className="sidebar">
        <Link to="/" className="brandmark"><span className="logo">D</span><div><b>Docuflow</b><span>Dashboard</span></div></Link>
        <nav className="sidenav">
          {canCreate && <NavLink to="/new" className="cta">{I.plus} New deal from MLS</NavLink>}
          <div className="sect">Work</div>
          <NavLink to="/" end>{I.pipeline} Pipeline</NavLink>
          <NavLink to="/due">{I.due} Due Soon</NavLink>
          {(isAdmin || me.is_superuser) && <div className="sect">Manage</div>}
          {isAdmin && <NavLink to="/team">{I.team} Team</NavLink>}
          {me.is_superuser && <NavLink to="/dev">{I.dev} Developer</NavLink>}
        </nav>
        <div className="usercard">
          <div className="who">
            <span className="avatar">{initials(me.first_name, me.last_name, me.email)}</span>
            <div><div className="name">{me.first_name} {me.last_name}</div><div className="role">{ROLE_LABEL[me.role]}</div></div>
          </div>
          <div className="tags">
            <span className={`pill ${me.docusign_env === 'production' ? 'prod' : 'test'}`} title="DocuSign account used for envelopes you send">DocuSign {me.docusign_env === 'production' ? 'PROD' : 'TEST'}</span>
          </div>
          <div className="userrow">
            <button className="themebtn" onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>{theme === 'dark' ? I.sun : I.moon} {theme === 'dark' ? 'Light mode' : 'Dark mode'}</button>
            <button className="link" onClick={() => { auth.clear(); setMe(null); navigate('/login') }}>Log out</button>
          </div>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="crumbs"><Link to="/">Docuflow</Link> / <b>{crumb}</b></div>
          <div className="actions">
            {me.is_superuser && <button className="secondary" onClick={() => setConsoleOpen((v) => !v)}>{I.console} {consoleOpen ? 'Hide console' : 'Console'}</button>}
          </div>
        </header>
        <div className="body">
          <main className="content">
            <Routes>
              <Route path="/" element={<Pipeline me={me} />} />
              <Route path="/due" element={<DueSoon me={me} />} />
              {canCreate && <Route path="/new" element={<NewDeal me={me} />} />}
              {isAdmin && <Route path="/team" element={<TeamPage me={me} />} />}
              {me.is_superuser && <Route path="/dev" element={<Dev me={me} />} />}
              <Route path="/deals/:id" element={<DealPage me={me} />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
          <Console open={consoleOpen} onClose={() => setConsoleOpen(false)} />
        </div>
      </div>
    </div>
  )
}
