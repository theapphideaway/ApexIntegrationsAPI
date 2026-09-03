import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, Link, useNavigate } from 'react-router-dom'
import { api, auth, type Me } from './api'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import DealPage from './pages/Deal'
import DueSoon from './pages/DueSoon'
import Dev from './pages/Dev'
import NewDeal from './pages/NewDeal'
import Console from './components/Console'

const ROLE_LABEL: Record<Me['role'], string> = { admin: 'Team Admin', tc: 'Transaction Coordinator', agent: 'Agent' }

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(auth.isLoggedIn)
  const navigate = useNavigate()
  const [consoleOpen, setConsoleOpen] = useState(false)

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

  return (
    <div className="shell">
      <header className="topbar">
        <nav className="nav">
          <Link to="/" className="brand">Apex · Deal Desk</Link>
          <Link to="/">Pipeline</Link>
          <Link to="/due">Due Soon</Link>
          {(me.role === 'agent' || me.is_superuser) && <Link to="/new" className="newdeal">+ New Deal</Link>}
          {me.is_superuser && <Link to="/dev" className="dev">Dev</Link>}
        </nav>
        <div className="who">
          <span>{me.first_name} {me.last_name}</span>
          <span className="pill">{ROLE_LABEL[me.role]}</span>
          <span className={`pill ${me.docusign_env === 'production' ? 'prod' : 'test'}`} title="DocuSign account used for envelopes you send">DocuSign {me.docusign_env === 'production' ? 'PROD' : 'TEST'}</span>
          {me.is_superuser && <button className="link" onClick={() => setConsoleOpen((v) => !v)}>{consoleOpen ? 'Hide console' : 'Console'}</button>}
          <button className="link" onClick={() => { auth.clear(); setMe(null); navigate('/login') }}>Log out</button>
        </div>
      </header>
      <div className={`body ${consoleOpen ? 'with-console' : ''}`}>
      <main className="content">
        <Routes>
          <Route path="/" element={<Pipeline me={me} />} />
          <Route path="/due" element={<DueSoon me={me} />} />
          {(me.role === 'agent' || me.is_superuser) && <Route path="/new" element={<NewDeal me={me} />} />}
          {me.is_superuser && <Route path="/dev" element={<Dev me={me} />} />}
          <Route path="/deals/:id" element={<DealPage me={me} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Console open={consoleOpen} onClose={() => setConsoleOpen(false)} />
      </div>
    </div>
  )
}
