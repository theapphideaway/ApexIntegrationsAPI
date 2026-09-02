import { useEffect, useState } from 'react'
import { Navigate, Route, Routes, Link, useNavigate } from 'react-router-dom'
import { api, auth, type Me } from './api'
import Login from './pages/Login'
import Pipeline from './pages/Pipeline'
import DealPage from './pages/Deal'

const ROLE_LABEL: Record<Me['role'], string> = { admin: 'Team Admin', tc: 'Transaction Coordinator', agent: 'Agent' }

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(auth.isLoggedIn)
  const navigate = useNavigate()

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
        <Link to="/" className="brand">Apex · Deal Desk</Link>
        <div className="who">
          <span>{me.first_name} {me.last_name}</span>
          <span className="pill">{ROLE_LABEL[me.role]}</span>
          <button className="link" onClick={() => { auth.clear(); setMe(null); navigate('/login') }}>Log out</button>
        </div>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<Pipeline me={me} />} />
          <Route path="/deals/:id" element={<DealPage me={me} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
