import { useState } from 'react'
import { api, auth, type Me } from '../api'

export default function Login({ onLoggedIn }: { onLoggedIn: (me: Me) => void }) {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [stage, setStage] = useState<'email' | 'code'>('email')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function sendCode(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try { await api.requestOtp(email.trim()); setStage('code') }
    catch (err) { setError(String(err)) } finally { setBusy(false) }
  }

  async function verify(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      const t = await api.verifyOtp(email.trim(), code.trim())
      auth.set(t.access, t.refresh)
      onLoggedIn(await api.me())
    } catch { setError('That code didn\'t work — request a new one and try again.') }
    finally { setBusy(false) }
  }

  return (
    <div className="center">
      <form className="card login" onSubmit={stage === 'email' ? sendCode : verify}>
        <h1>Apex · Deal Desk</h1>
        {stage === 'email' ? (
          <>
            <label>Work email<input type="email" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@yourteam.com" /></label>
            <button className="primary" disabled={busy}>{busy ? 'Sending…' : 'Send login code'}</button>
          </>
        ) : (
          <>
            <p className="muted">We emailed a 6-digit code to <b>{email}</b>.</p>
            <label>Login code<input inputMode="numeric" autoFocus required value={code} onChange={(e) => setCode(e.target.value)} placeholder="000000" /></label>
            <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
            <button type="button" className="link" onClick={() => setStage('email')}>Use a different email</button>
          </>
        )}
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  )
}
