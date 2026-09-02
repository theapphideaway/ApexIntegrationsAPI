import { useState } from 'react'
import { api, type Deal } from '../api'

/** RE-13 counter offer: either respond to a received seller counter (buyer
 *  accepts by signing our transcription of it) or send a new buyer counter.
 *  Sent to the buyer for signature under the deal's agent identity. */
export default function CounterForm({ deal, mode, nextNumber, onClose, onSent }:
  { deal: Deal; mode: 'respond' | 'new'; nextNumber: number; onClose: () => void; onSent: () => void }) {
  const [isSellerCounter, setIsSellerCounter] = useState(mode === 'respond')
  const [terms, setTerms] = useState('')
  const [expDate, setExpDate] = useState('')
  const [expTime, setExpTime] = useState('5:00 PM')
  const [newPrice, setNewPrice] = useState('')
  const [newClosing, setNewClosing] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      const resulting: Record<string, unknown> = {}
      if (newPrice) resulting.offerPrice = Number(newPrice.replace(/[^0-9.]/g, ''))
      if (newClosing) resulting.closingDate = new Date(newClosing).toISOString()
      await api.sendDocument(deal.id, {
        doc_type: 're_13',
        fields: {
          counterOfferNumber: String(nextNumber),
          isSellerCounter,
          counterOfferText: terms,
          offerExpirationDate: expDate ? new Date(expDate).toISOString() : '',
          offerExpirationTime: expTime,
          psaDate: deal.acceptance_date || '',
        },
        resulting_terms: Object.keys(resulting).length ? resulting : undefined,
      })
      onSent()
    } catch (err) { setError(String(err)) } finally { setBusy(false) }
  }

  return (
    <div className="modal" onClick={onClose}>
      <form className="card dialog" onClick={(e) => e.stopPropagation()} onSubmit={send}>
        <h2>{mode === 'respond' ? 'Respond to counter offer' : 'Send a counter offer'} · RE-13 #{nextNumber}</h2>
        <p className="muted small">{deal.property_address} · buyer: {deal.buyer_names}</p>
        <label>Originated by
          <select value={isSellerCounter ? 'seller' : 'buyer'} onChange={(e) => setIsSellerCounter(e.target.value === 'seller')}>
            <option value="seller">Seller&apos;s counter — the buyer signs to ACCEPT these terms</option>
            <option value="buyer">Buyer&apos;s counter — the buyer signs, then it goes to the listing agent</option>
          </select>
        </label>
        <label>Counter offer terms (exactly as they should print)
          <textarea required rows={6} value={terms} onChange={(e) => setTerms(e.target.value)} placeholder={isSellerCounter ? "Type the seller's terms from their counter…" : 'Type the new terms…'} />
        </label>
        <div className="row">
          <label>Response deadline<input type="date" value={expDate} onChange={(e) => setExpDate(e.target.value)} /></label>
          <label>Time<input value={expTime} onChange={(e) => setExpTime(e.target.value)} placeholder="5:00 PM" /></label>
        </div>
        <fieldset>
          <legend>Resulting terms (if this counter changes them)</legend>
          <div className="row">
            <label>New purchase price<input inputMode="decimal" value={newPrice} onChange={(e) => setNewPrice(e.target.value)} placeholder="e.g. 415000" /></label>
            <label>New closing date<input type="date" value={newClosing} onChange={(e) => setNewClosing(e.target.value)} /></label>
          </div>
          <p className="muted small">Updating these recomputes the deal&apos;s deadlines on every device.</p>
        </fieldset>
        {error && <p className="error">{error}</p>}
        <div className="row end">
          <button type="button" className="link" onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy || !terms.trim()}>{busy ? 'Sending to DocuSign…' : 'Send to buyer for signature'}</button>
        </div>
      </form>
    </div>
  )
}
