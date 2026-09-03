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
    } catch { setError('That code didn\'t work. Request a new one and try again.') }
    finally { setBusy(false) }
  }

  return (
    <div className="auth">
      <section className="authbrand">
        <div className="brandmark" style={{ padding: 0 }}><span className="logo">A</span><div><b>Apex Deal Desk</b><span>TC platform</span></div></div>
        <div>
          <h2>Every deal, every deadline, every document — in one place.</h2>
          <p>From MLS listing to executed packet: prefilled Idaho forms, DocuSign signatures, counter offers, and a live checklist your whole team works from.</p>
          <ul>
            <li>Start a deal from the live MLS in under a minute</li>
            <li>Team pipeline and deadline board for TCs</li>
            <li>Drag-and-drop documents, counters signed in a click</li>
          </ul>
        </div>
        <p className="small" style={{ color: '#7f95ab' }}>© Apex Integrations</p>
      </section>
      <section className="authform">
        <form className="card login" onSubmit={stage === 'email' ? sendCode : verify}>
          <h1>{stage === 'email' ? 'Sign in' : 'Check your email'}</h1>
          {stage === 'email' ? (
            <>
              <p className="lead">Use your work email. We&apos;ll send a one-time code — no password to remember.</p>
              <label>Work email<input type="email" autoFocus required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@yourteam.com" /></label>
              <button className="primary" disabled={busy}>{busy ? 'Sending…' : 'Send login code'}</button>
            </>
          ) : (
            <>
              <p className="lead">We emailed a 6-digit code to <b>{email}</b>.</p>
              <label>Login code<input className="codeinput" inputMode="numeric" autoComplete="one-time-code" autoFocus required value={code} onChange={(e) => setCode(e.target.value)} placeholder="••••••" /></label>
              <button className="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
              <button type="button" className="link" onClick={() => setStage('email')}>Use a different email</button>
            </>
          )}
          {error && <p className="error">{error}</p>}
        </form>
      </section>
    </div>
  )
}
