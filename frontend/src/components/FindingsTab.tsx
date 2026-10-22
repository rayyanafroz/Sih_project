import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fileUrl, type ApplicationDetail, type Evidence, type Finding } from '../api'
import { useSession } from '../context'
import { fieldLabel, fmtDateTime, humanize, useApi } from '../util'
import { Badge, Button, DocIcon, Empty, ErrorBox, Loading, MockTag } from './ui'

const TYPE_LABELS: Record<string, string> = {
  MISSING_DOCUMENT: 'Missing document', EXPIRED_DOCUMENT: 'Expiry', CONSISTENCY: 'Consistency',
  ANOMALY: 'Potential anomaly', VERIFICATION: 'Verification', REGULATORY: 'Regulatory', INFRASTRUCTURE: 'Infrastructure',
}
const OPEN = ['OPEN', 'CLARIFICATION_REQUESTED', 'ESCALATED']
const FILTERS = [
  { key: 'open', label: 'Open', match: (f: Finding) => OPEN.includes(f.status) },
  { key: 'reviewed', label: 'Reviewed', match: (f: Finding) => f.status === 'REVIEWED' },
  { key: 'cleared', label: 'Cleared on re-run', match: (f: Finding) => f.status === 'AUTO_CLEARED' },
  { key: 'all', label: 'All', match: () => true },
]
const ACTION_LABELS: Record<string, string> = {
  request_clarification: 'Requested clarification', mark_reviewed: 'Marked reviewed', escalate: 'Escalated', reopen: 'Re-opened',
}

function evidenceUrl(e: Evidence) {
  return fileUrl(`/documents/${e.document_id}/pages/${e.page || 1}/image`, e.bbox ? { boxes: e.bbox.join(',') } : {})
}

export function EvidenceViewer({ evidence }: { evidence: Evidence[] }) {
  const docs = evidence.filter(e => e.kind === 'document')
  const [active, setActive] = useState(0)
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const current = docs[active] || docs[0]
  const src = current ? evidenceUrl(current) : ''

  return (
    <div className="evidence-doc">
      {current ? (
        <>
          <div className="row" style={{ fontSize: 12 }}>
            <DocIcon /><b>{current.filename}</b><span className="faint">· Page {current.page || 1}</span>
            <span className="spacer" />
            <a href={fileUrl(`/documents/${current.document_id}/file`)} target="_blank" rel="noreferrer">Open original ↗</a>
          </div>
          <div className="evidence-img-wrap">
            {failedSrc === src ? <div className="empty" style={{ border: 'none' }}>Page preview unavailable.</div> : (
              <img src={src} alt={`${current.filename} page ${current.page} with highlighted evidence`}
                   onError={() => setFailedSrc(src)} />
            )}
          </div>
          {current.bbox && <div className="help">Highlighted region: the exact text the value was extracted from.</div>}
          {docs.length > 1 && (
            <div className="chip-row">
              {docs.map((d, i) => (
                <button key={i} className={`chip ${i === active ? 'active' : ''}`} onClick={() => setActive(i)}>
                  {d.filename} p.{d.page || 1}
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="empty" style={{ margin: 'auto', border: 'none', background: 'transparent' }}>
          This finding is based on records and checklists rather than a single page. See the evidence list.
        </div>
      )}
    </div>
  )
}

function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      {evidence.map((e, i) => (
        <div key={i} className="ev-item">
          <span className="ev-kind">{e.kind === 'application_form' ? 'Form' : e.kind === 'record' ? 'Record' : humanize(e.kind)}</span>
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 500 }}>{e.label}</div>
            {e.value && <div className="muted" style={{ overflowWrap: 'anywhere' }}>{e.value}</div>}
            {e.kind === 'record' && <div className="faint" style={{ fontSize: 12 }}>{e.source}{e.reference ? ` · ref ${e.reference}` : ''}</div>}
            {e.kind === 'document' && <div className="faint" style={{ fontSize: 12 }}>Page {e.page || 1}{e.field ? ` · ${fieldLabel(e.field)}` : ''}</div>}
            {e.kind === 'verification' && <div className="faint" style={{ fontSize: 12 }}>{e.method}</div>}
          </div>
          {e.is_mock && <MockTag />}
        </div>
      ))}
    </div>
  )
}

function FindingDetail({ findingId, app, onChanged }: { findingId: number; app: ApplicationDetail; onChanged: () => void }) {
  const { can, toast } = useSession()
  const { data: f, error, loading, reload, setData } = useApi(() => api.get<Finding>(`/findings/${findingId}`), [findingId])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState<string | null>(null)

  if (loading && !f) return <div className="card"><Loading /></div>
  if (error || !f) return <ErrorBox error={error || 'Failed to load finding'} onRetry={reload} />

  const locked = !!app.outcome || f.status === 'AUTO_CLEARED'
  const canAct = can('finding:act') && !locked
  async function act(action: string) {
    setBusy(action)
    try {
      const updated = await api.post<Finding>(`/findings/${findingId}/actions`, { action, note })
      setData(updated)
      setNote('')
      toast(`${ACTION_LABELS[action]} — recorded in audit trail`, 'success')
      onChanged()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }
  const tone = f.severity === 'CRITICAL' ? 'critical' : f.severity === 'WARNING' ? 'warning' : 'info'

  return (
    <div className="evidence-split fade-up">
      <EvidenceViewer key={f.id} evidence={f.evidence} />
      <div className="evidence-detail">
        <div className="row wrap">
          <Badge value={f.severity} label={f.severity === 'INFO' ? 'Pending' : undefined} />
          <span className="tag">{TYPE_LABELS[f.finding_type] || f.finding_type}</span>
          <span className="spacer" />
          <Badge value={f.status} />
        </div>
        <div>
          <h3 style={{ fontSize: 19, lineHeight: 1.3 }}>{f.title}</h3>
          <p className="muted" style={{ marginTop: 8 }}>{f.description}</p>
        </div>
        <div className="flag-box">
          <h4 style={{ marginBottom: 10 }}>Why was this flagged?</h4>
          {f.expected_value && <div className="flag-row"><span className="flag-label">Expected</span><span className="flag-value">{f.expected_value}</span></div>}
          {f.actual_value && <div className="flag-row"><span className="flag-label">Observed</span><span className="flag-value" style={{ color: 'var(--accent)' }}>{f.actual_value}</span></div>}
          <div className="flag-row"><span className="flag-label">Rule</span><span className="flag-value">{f.rule_id} · v{f.rule_version}</span></div>
          {f.confidence !== null && <div className="flag-row"><span className="flag-label">Confidence</span><span className="flag-value">{Math.round(f.confidence * 100)}%</span></div>}
          <div className="flag-row"><span className="flag-label">Detected</span><span className="flag-value">{fmtDateTime(f.created_at)}</span></div>
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Evidence</h4>
          <EvidenceList evidence={f.evidence} />
        </div>
        <div className={`action-box tone-${tone}`}>Recommended next step: {f.recommended_action}</div>

        <div>
          <h4 style={{ marginBottom: 8 }}>Officer action</h4>
          {locked ? (
            <p className="help">{app.outcome ? 'An outcome has been recorded for this application.' : 'Cleared automatically by a later pre-scrutiny run.'}</p>
          ) : !can('finding:act') ? (
            <p className="help">Your role can view findings but not act on them.</p>
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              <textarea className="textarea" placeholder="Note for the record (required) — e.g. what was checked or what the institution must provide"
                        value={note} onChange={e => setNote(e.target.value)} aria-label="Officer note" />
              <div className="row wrap">
                {f.status === 'OPEN' || f.status === 'ESCALATED' || f.status === 'CLARIFICATION_REQUESTED' ? <>
                  <Button busy={busy === 'request_clarification'} disabled={!canAct || note.trim().length < 3} onClick={() => act('request_clarification')}>Request clarification</Button>
                  <Button className="btn-secondary" busy={busy === 'mark_reviewed'} disabled={!canAct || note.trim().length < 3} onClick={() => act('mark_reviewed')}>Mark reviewed</Button>
                  {f.status !== 'ESCALATED' && <Button className="btn-secondary" busy={busy === 'escalate'} disabled={!canAct || note.trim().length < 3} onClick={() => act('escalate')}>Escalate</Button>}
                </> : <Button className="btn-secondary" busy={busy === 'reopen'} onClick={() => act('reopen')}>Re-open</Button>}
              </div>
            </div>
          )}
        </div>

        {(f.actions?.length || f.resolution_note) ? (
          <div>
            <h4 style={{ marginBottom: 8 }}>History</h4>
            <div className="history">
              {f.actions?.map(a => (
                <div key={a.id} className="history-item">
                  <div><b>{ACTION_LABELS[a.action] || a.action}</b> <span className="faint">· {a.actor} · {fmtDateTime(a.at)}</span></div>
                  {a.note && <div className="muted">{a.note}</div>}
                </div>
              ))}
              {f.status === 'AUTO_CLEARED' && <div className="history-item"><b>Cleared</b> <span className="faint">· {f.resolution_note}</span></div>}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

export default function FindingsTab({ app, version, selected, onSelect, onChanged }: {
  app: ApplicationDetail; version: number; selected: number | null; onSelect: (id: number | null) => void; onChanged: () => void
}) {
  const [filter, setFilter] = useState('open')
  const { data, error, loading, reload } = useApi(() => api.get<Finding[]>(`/applications/${app.id}/findings`), [app.id, version])
  const list = useMemo(() => (data || []).filter(FILTERS.find(x => x.key === filter)!.match), [data, filter])

  useEffect(() => {
    if (!data) return
    if (selected && data.some(f => f.id === selected)) {
      if (!list.some(f => f.id === selected)) setFilter('all')
      return
    }
    if (list.length) onSelect(list[0].id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!app.last_completed_run) {
    return <Empty>No findings yet. Upload documents in the <Link to={`/applications/${app.id}/documents`}>Documents</Link> tab, then run AI pre-scrutiny.</Empty>
  }

  return (
    <div className="findings-layout">
      <div>
        <div className="chip-row" style={{ marginBottom: 12 }}>
          {FILTERS.map(x => (
            <button key={x.key} className={`chip ${filter === x.key ? 'active' : ''}`} onClick={() => setFilter(x.key)}>
              {x.label} ({(data || []).filter(x.match).length})
            </button>
          ))}
        </div>
        <div className="finding-list">
          {list.length === 0 && <Empty>{filter === 'open' ? 'No open findings — ready for officer decision.' : 'Nothing here.'}</Empty>}
          {list.map(f => (
            <button key={f.id} className={`finding-card sev-${f.severity} ${selected === f.id ? 'selected' : ''} ${OPEN.includes(f.status) ? '' : 'resolved'}`}
                    onClick={() => onSelect(f.id)}>
              <div className="row" style={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div className="finding-title">{f.title}</div>
              </div>
              <div className="finding-meta">
                <Badge value={f.severity} label={f.severity === 'INFO' ? 'Pending' : undefined} />
                {f.status !== 'OPEN' && <Badge value={f.status} />}
                <span>{TYPE_LABELS[f.finding_type]}</span>
              </div>
              {f.evidence.find(e => e.kind === 'document') && (
                <div className="finding-meta"><DocIcon />{f.evidence.find(e => e.kind === 'document')!.filename} · p.{f.evidence.find(e => e.kind === 'document')!.page}</div>
              )}
            </button>
          ))}
        </div>
      </div>
      <div>
        {selected && data?.some(f => f.id === selected)
          ? <FindingDetail key={selected} findingId={selected} app={app} onChanged={() => { reload(true); onChanged() }} />
          : <Empty>Select a finding to see its evidence.</Empty>}
      </div>
    </div>
  )
}
