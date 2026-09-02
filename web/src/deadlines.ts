// Port of the iOS TransactionTimeline engine — same rules, so the web
// deadline board matches the phone's Key Deadlines card exactly.
import type { Deal } from './api'

export type Deadline = { title: string; date: Date; note: string }

const addDays = (d: Date, n: number) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const asDate = (v: unknown): Date | null => { if (!v) return null; const d = new Date(String(v)); return isNaN(d.getTime()) ? null : d }
const asInt = (v: unknown): number | null => (v === null || v === undefined || v === '') ? null : Number(v)

/** Acceptance = server acceptance_date, else updated_at for executed deals (mirrors iOS). */
export function acceptanceDate(deal: Deal): Date | null {
  if (deal.acceptance_date) return asDate(deal.acceptance_date)
  if (['fully_executed', 'executed', 'signed_by_buyers'].includes(deal.status)) return asDate(deal.updated_at)
  return null
}

export function computeDeadlines(deal: Deal): Deadline[] {
  const acc = acceptanceDate(deal)
  const f = deal.form_snapshot || {}
  if (!acc) return []
  const out: Deadline[] = []
  const em = asInt(f.earnestMoneyDeliveredDays)
  if (em !== null) out.push({ title: 'Earnest money due', date: addDays(acc, em), note: `Acceptance + ${em} days` })
  const tc = asInt(f.titleCommitmentDays)
  if (tc !== null) {
    const title = addDays(acc, tc)
    out.push({ title: 'Title commitment due', date: title, note: `Acceptance + ${tc} days` })
    const obj = asInt(f.titleObjectionDays)
    if (obj !== null) out.push({ title: 'Title objection deadline', date: addDays(title, obj), note: `Title commitment + ${obj} days` })
  }
  const insp = asInt(f.inspectionPeriod)
  if (insp !== null) {
    const inspDate = addDays(acc, insp)
    out.push({ title: 'Inspection deadline', date: inspDate, note: `Acceptance + ${insp} days` })
    const resp = asInt(f.inspectionSellerResponseDays)
    if (resp !== null) out.push({ title: 'Inspection seller response', date: addDays(inspDate, resp), note: `Inspection + ${resp} days` })
  }
  out.push({ title: 'Appraisal ordered (target)', date: addDays(acc, 13), note: '≈ Day 13' })
  out.push({ title: 'Appraisal received (target)', date: addDays(acc, 18), note: '≈ Day 18' })
  const closing = asDate(f.closingDate)
  if (closing) out.push({ title: 'Closing', date: closing, note: 'Fixed date' })
  return out.sort((a, b) => a.date.getTime() - b.date.getTime())
}

export function urgency(date: Date): 'overdue' | 'soon' | 'later' {
  const now = Date.now()
  if (date.getTime() < now) return 'overdue'
  if (date.getTime() < now + 3 * 86400_000) return 'soon'
  return 'later'
}
