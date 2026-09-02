// Mirrors the iOS TC checklist template EXACTLY (same task keys) so statuses
// written here show up on the agent's phone and vice versa.
export const STATUSES = ['Not Started', 'In Progress', 'Waiting', 'Complete', 'N/A'] as const
export type Status = typeof STATUSES[number]
export const isDone = (s: string) => s === 'Complete' || s === 'N/A'

export type Task = { key: string; title: string }
export type Phase = { title: string; tasks: Task[] }

export const PHASES: Phase[] = [
  { title: 'Phase 1 · Under Contract & Escrow Intake', tasks: [
    { key: 'p1.1', title: 'Contract Execution Audit' },
    { key: 'p1.2', title: 'Buyer Distribution' },
    { key: 'p1.3', title: 'Opening Escrow' },
    { key: 'p1.4', title: 'Lender Delivery' },
    { key: 'p1.5', title: 'Earnest Money Compliance' },
  ]},
  { title: 'Phase 2 · Title, Appraisal & Lending', tasks: [
    { key: 'p2.1', title: 'Title Commitment Review' },
    { key: 'p2.2', title: 'Transaction Fee Routing' },
    { key: 'p2.3', title: 'Appraisal Ordered (Day 13)' },
    { key: 'p2.4', title: 'Appraisal Received (Day 18)' },
  ]},
  { title: 'Phase 3 · Inspection & Defect Response (RE-10)', tasks: [
    { key: 'p3.1', title: 'Primary RE-10 Execution' },
    { key: 'p3.2', title: 'Secondary RE-10 Handling' },
    { key: 'p3.3', title: 'Vendor Distribution' },
    { key: 'p3.4', title: 'Repair Documentation Collection' },
    { key: 'p3.5', title: 'Invoicing for Settlement' },
  ]},
  { title: 'Phase 4 · Settlement, Closing & Funding', tasks: [
    { key: 'p4.1', title: 'Commission Instructions' },
    { key: 'p4.2', title: 'Settlement Statement Audit' },
    { key: 'p4.3', title: 'Client Closing Delivery' },
    { key: 'p4.4', title: 'Post-Closing Retrieval' },
    { key: 'p4.5', title: 'Financial Reconciliation' },
  ]},
]
