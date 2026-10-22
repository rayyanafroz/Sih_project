import { useMemo, useState } from 'react'
import type { AuditEntry } from '../api'
import { fmtDateTime } from '../util'
import { Empty } from './ui'

const FILTERS = [
  { key: 'all', label: 'All events', match: () => true },
  { key: 'officer', label: 'Officer actions', match: (e: AuditEntry) => e.actor_type === 'user' },
  { key: 'system', label: 'System', match: (e: AuditEntry) => e.actor_type === 'system' },
  { key: 'finding', label: 'Findings', match: (e: AuditEntry) => e.action.startsWith('finding.') },
  { key: 'verification', label: 'Verification', match: (e: AuditEntry) => e.action.startsWith('verification.') },
  { key: 'rules', label: 'Rules & runs', match: (e: AuditEntry) => /^(rule|rules|prescrutiny|settings|source)\./.test(e.action) },
]

function nodeColor(e: AuditEntry) {
  if (e.actor_type === 'user') return 'var(--accent)'
  if (e.action.startsWith('finding.created')) return 'var(--warning)'
  if (e.action.startsWith('verification')) return 'var(--info)'
  return 'var(--border)'
}

export default function Timeline({ entries, showApp }: { entries: AuditEntry[]; showApp?: boolean }) {
  const [filter, setFilter] = useState('all')
  const list = useMemo(() => entries.filter(FILTERS.find(f => f.key === filter)!.match), [entries, filter])
  return (
    <div>
      <div className="chip-row" style={{ marginBottom: 16 }}>
        {FILTERS.map(f => (
          <button key={f.key} className={`chip ${filter === f.key ? 'active' : ''}`} onClick={() => setFilter(f.key)}>
            {f.label} ({entries.filter(f.match).length})
          </button>
        ))}
      </div>
      {list.length === 0 ? <Empty>No events.</Empty> : (
        <div className="timeline">
          {list.map(e => (
            <div key={e.id} className="audit-entry">
              <div className="audit-node" style={{ background: nodeColor(e) }} />
              <div className="audit-time">{fmtDateTime(e.at)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: e.actor_type === 'user' ? 500 : 400, color: e.actor_type === 'user' ? 'var(--ink)' : 'var(--muted)' }}>{e.summary}</div>
                <div className="faint" style={{ fontSize: 12 }}>
                  <span className="mono">{e.action}</span>
                  {typeof e.details?.note === 'string' && e.details.note && <> · “{e.details.note}”</>}
                  {typeof e.details?.rule_version === 'number' && <> · rule v{e.details.rule_version}</>}
                </div>
              </div>
              {showApp && e.application_code && <span className="tag">{e.application_code}</span>}
              {e.actor_type === 'user' ? <span className="officer-tag">{e.actor}</span> : <span className="system-tag">System</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
