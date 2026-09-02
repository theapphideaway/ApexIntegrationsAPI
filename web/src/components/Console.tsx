import { useEffect, useState } from 'react'
import { consoleBus, type ConsoleEntry } from '../api'

/** Side console: every API request/response the portal makes, newest first. */
export default function Console({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [entries, setEntries] = useState<ConsoleEntry[]>([])
  const [expanded, setExpanded] = useState<number | null>(null)
  useEffect(() => consoleBus.subscribe((e) => setEntries((prev) => [e, ...prev].slice(0, 200))), [])
  if (!open) return null
  return (
    <aside className="console">
      <div className="conhead">
        <b>Console</b><span className="muted small">{entries.length} calls</span>
        <span className="spacer" />
        <button className="link" onClick={() => setEntries([])}>Clear</button>
        <button className="link" onClick={onClose}>Close</button>
      </div>
      <div className="conbody">
        {entries.length === 0 && <p className="muted small">API traffic will appear here.</p>}
        {entries.map((e) => {
          const ok = typeof e.status === 'number' && e.status < 400
          const isOpen = expanded === e.id
          return (
            <div key={e.id} className={`conentry ${ok ? '' : 'bad'}`}>
              <div className="conline" onClick={() => setExpanded(isOpen ? null : e.id)}>
                <span className={`status ${ok ? 'ok' : 'bad'}`}>{e.status}</span>
                <span className="method">{e.method}</span>
                <span className="path" title={e.path}>{e.path}</span>
                <span className="muted small">{e.ms.toFixed(0)}ms · {e.at.toLocaleTimeString()}</span>
              </div>
              {isOpen && (
                <div className="condetail">
                  {e.request !== undefined && <><div className="muted small">request</div><pre>{JSON.stringify(e.request, null, 2)}</pre></>}
                  <div className="muted small">response</div>
                  <pre>{typeof e.response === 'string' ? e.response : JSON.stringify(e.response, null, 2)}</pre>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </aside>
  )
}
