import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, type ApplicationDetail, type AuditEntry, type Run } from '../api'
import ComplianceTab from '../components/ComplianceTab'
import DocumentsTab from '../components/DocumentsTab'
import FindingsTab from '../components/FindingsTab'
import Scanner from '../components/Scanner'
import Timeline from '../components/Timeline'
import { Badge, Button, Disclaimer, ErrorBox, Loading, Modal } from '../components/ui'
import VerificationTab from '../components/VerificationTab'
import { useSession } from '../context'
import { fmtDate, fmtDateTime, humanize, useApi } from '../util'

const OUTCOMES = [
  { code: 'RECOMMEND_APPROVAL', label: 'Recommend approval', help: 'Requirements are met; forward for approval.' },
  { code: 'ISSUE_DEFICIENCY_LETTER', label: 'Issue deficiency letter', help: 'Ask the institution to rectify the listed deficiencies.' },
  { code: 'REFER_FOR_INSPECTION', label: 'Refer for physical inspection', help: 'Evidence cannot be confirmed remotely.' },
  { code: 'REFER_TO_COMMITTEE', label: 'Refer to scrutiny committee', help: 'Escalate for committee consideration.' },
]

function OutcomeModal({ app, onClose, onSaved }: { app: ApplicationDetail; onClose: () => void; onSaved: () => void }) {
  const { toast } = useSession()
  const [outcome, setOutcome] = useState(app.findings.critical ? 'ISSUE_DEFICIENCY_LETTER' : 'RECOMMEND_APPROVAL')
  const [note, setNote] = useState('')
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const needsAck = outcome === 'RECOMMEND_APPROVAL' && app.findings.critical > 0

  async function save() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/applications/${app.id}/outcome`, { outcome, note, acknowledge_open_findings: ack })
      toast('Outcome recorded by officer — audit trail updated', 'success')
      onSaved()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Record officer outcome — ${app.code}`} onClose={onClose} footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <Button busy={busy} disabled={note.trim().length < 5 || (needsAck && !ack)} onClick={save}>Record outcome</Button>
    </>}>
      <Disclaimer />
      <div className="row wrap" style={{ gap: 16 }}>
        <span><b className="nums">{app.findings.critical}</b> <span className="muted">critical open</span></span>
        <span><b className="nums">{app.findings.warning}</b> <span className="muted">warnings open</span></span>
        <span><b className="nums">{app.findings.reviewed}</b> <span className="muted">reviewed</span></span>
        <span><b className="nums">{app.rules.passed}/{app.rules.evaluated}</b> <span className="muted">rules passed</span></span>
      </div>
      <div className="stack" style={{ gap: 8 }}>
        {OUTCOMES.map(o => (
          <label key={o.code} className="demo-account" style={{ cursor: 'pointer', borderColor: outcome === o.code ? 'var(--accent)' : undefined }}>
            <div className="row" style={{ gap: 10 }}>
              <input type="radio" name="outcome" checked={outcome === o.code} onChange={() => setOutcome(o.code)} style={{ accentColor: 'var(--accent)' }} />
              <div><div style={{ fontWeight: 500 }}>{o.label}</div><div className="faint" style={{ fontSize: 12 }}>{o.help}</div></div>
            </div>
          </label>
        ))}
      </div>
      <div className="field">
        <label>Officer's reasoning (required, stored in the audit trail)</label>
        <textarea className="textarea" value={note} onChange={e => setNote(e.target.value)}
                  placeholder="Summarise the evidence relied on and any conditions." />
      </div>
      {needsAck && (
        <label className="checkbox">
          <input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />
          I have reviewed the {app.findings.critical} open critical finding(s) and take responsibility for this outcome.
        </label>
      )}
      {error && <ErrorBox error={error} />}
    </Modal>
  )
}

const TABS = [
  { key: '', label: 'Findings' },
  { key: 'documents', label: 'Documents' },
  { key: 'verification', label: 'Verification' },
  { key: 'compliance', label: 'Compliance checklist' },
  { key: 'audit', label: 'Audit trail' },
]

export default function WorkspacePage() {
  const { id, tab = '' } = useParams()
  const appId = Number(id)
  const nav = useNavigate()
  const [params, setParams] = useSearchParams()
  const { can, toast } = useSession()
  const [version, setVersion] = useState(0)
  const [scanRun, setScanRun] = useState<Run | null>(null)
  const [starting, setStarting] = useState(false)
  const [outcomeOpen, setOutcomeOpen] = useState(false)
  const { data: app, error, loading, reload } = useApi(() => api.get<ApplicationDetail>(`/applications/${appId}`), [appId])
  const audit = useApi(() => (tab === 'audit' ? api.get<AuditEntry[]>(`/applications/${appId}/audit`) : Promise.resolve([])), [appId, tab, version])

  const refresh = useCallback(() => { reload(true); setVersion(v => v + 1) }, [reload])
  const selectedFinding = params.get('finding') ? Number(params.get('finding')) : null
  const selectFinding = (fid: number | null) => setParams(fid ? { finding: String(fid) } : {}, { replace: true })

  useEffect(() => {
    if (app?.last_run?.status === 'RUNNING' && !scanRun) setScanRun(app.last_run)
  }, [app, scanRun])

  async function startRun() {
    setStarting(true)
    try {
      const run = await api.post<Run>(`/applications/${appId}/prescrutiny`)
      setScanRun(run)
    } catch (e) { toast((e as Error).message, 'error') } finally { setStarting(false) }
  }

  if (loading && !app) return <div className="page"><Loading /></div>
  if (error || !app) return <div className="page"><ErrorBox error={error || 'Not found'} onRetry={reload} /></div>

  const canRun = can('prescrutiny:run') && !app.outcome && app.documents.total > 0
  const hasRun = !!app.last_completed_run
  const tabCounts: Record<string, { n: string | number; alert?: boolean }> = {
    '': { n: app.findings.open, alert: app.findings.critical > 0 },
    documents: { n: app.documents.total },
    verification: { n: app.verification.total ? `${app.verification.verified}/${app.verification.total}` : 0 },
    compliance: { n: hasRun ? `${app.rules.passed}/${app.rules.evaluated}` : '—' },
  }

  return (
    <div className="page wide fade-up">
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow"><Link to="/applications" className="faint">Applications</Link> / {app.category_label}</div>
          <div className="row wrap" style={{ gap: 14 }}>
            <h1 className="title">{app.code}</h1>
            <Badge value={app.status} />
          </div>
          <div style={{ fontSize: 16, marginTop: 4 }} className="muted">{app.institution.name}</div>
          <div className="row wrap faint" style={{ gap: 18, marginTop: 6, fontSize: 13 }}>
            <span>AICTE ID {app.institution.aicte_id}</span><span>Academic year {app.academic_year}</span>
            <span>Submitted {fmtDate(app.submitted_at)}</span>
            {app.last_completed_run && <span>Last pre-scrutiny {fmtDateTime(app.last_completed_run.finished_at)}</span>}
          </div>
        </div>
        <span className="spacer" />
        <div className="row wrap" style={{ justifyContent: 'flex-end' }}>
          <Link className="btn btn-secondary" to={`/applications/${app.id}/report`}>Validation report</Link>
          {can('outcome:record') && !app.outcome && (
            <button className="btn btn-secondary" disabled={!hasRun || app.status === 'PROCESSING'} onClick={() => setOutcomeOpen(true)}
                    title={hasRun ? '' : 'Run pre-scrutiny first'}>Record outcome</button>
          )}
          {can('prescrutiny:run') && !app.outcome && (
            <Button busy={starting} disabled={!canRun || app.status === 'PROCESSING'} onClick={startRun}
                    title={app.documents.total ? '' : 'Upload documents first'}>
              {hasRun ? 'Re-run AI pre-scrutiny' : 'Run AI pre-scrutiny'}
            </Button>
          )}
        </div>
      </div>

      {app.outcome && (
        <div className="banner tone-success" style={{ marginTop: 18 }}>
          <b>Officer outcome: {humanize(app.outcome)}</b>
          <span>— {app.outcome_by?.name}, {fmtDateTime(app.outcome_at)}. “{app.outcome_note}”</span>
        </div>
      )}
      {app.needs_rerun && !app.outcome && (
        <div className="banner tone-info" style={{ marginTop: 18 }}>
          {hasRun ? 'Documents changed since the last pre-scrutiny. Re-run to update findings.' : `${app.documents.total} document(s) uploaded and ready for AI pre-scrutiny.`}
          <span className="spacer" />
          {can('prescrutiny:run') && <Button className="btn-primary btn-sm" busy={starting} onClick={startRun}>{hasRun ? 'Re-run now' : 'Run now'}</Button>}
        </div>
      )}

      <div className="metric-grid" style={{ marginTop: 22 }}>
        <div className="metric-cell"><div className="metric-value">{app.documents.processed} / {app.documents.total}</div><div className="metric-label">Documents processed</div>
          {app.documents.failed > 0 && <div className="metric-sub" style={{ color: 'var(--accent)' }}>{app.documents.failed} failed</div>}</div>
        <div className="metric-cell"><div className="metric-value">{hasRun ? `${app.rules.passed} / ${app.rules.evaluated}` : '—'}</div><div className="metric-label">Rules passed</div></div>
        <div className="metric-cell"><div className="metric-value">{app.verification.total ? `${app.verification.verified} / ${app.verification.total}` : '—'}</div><div className="metric-label">Sources verified</div>
          {app.verification.pending > 0 && <div className="metric-sub">{app.verification.pending} awaiting confirmation</div>}</div>
        <div className="metric-cell"><div className="metric-value" style={{ color: app.findings.critical ? 'var(--accent)' : undefined }}>{hasRun ? app.findings.open : '—'}</div><div className="metric-label">Open findings</div>
          {hasRun && <div className="metric-sub">{app.findings.critical} critical · {app.findings.warning} warning · {app.findings.info} pending</div>}</div>
      </div>
      <div style={{ marginTop: 14 }}><Disclaimer /></div>

      <div className="tabs" role="tablist">
        {TABS.map(t => (
          <Link key={t.key} role="tab" aria-selected={tab === t.key} className={`tab ${tab === t.key ? 'active' : ''}`}
                to={`/applications/${app.id}${t.key ? `/${t.key}` : ''}`}>
            {t.label}
            {tabCounts[t.key] !== undefined && <span className={`tab-count ${tabCounts[t.key].alert ? 'alert' : ''}`}>{tabCounts[t.key].n}</span>}
          </Link>
        ))}
      </div>

      {tab === '' && <FindingsTab app={app} version={version} selected={selectedFinding} onSelect={selectFinding} onChanged={refresh} />}
      {tab === 'documents' && <DocumentsTab app={app} version={version} onChanged={refresh} />}
      {tab === 'verification' && <VerificationTab app={app} version={version} onChanged={refresh} />}
      {tab === 'compliance' && <ComplianceTab app={app} version={version} onOpenFinding={fid => nav(`/applications/${app.id}?finding=${fid}`)} />}
      {tab === 'audit' && (
        <div style={{ marginTop: 20 }}>
          {audit.loading && !audit.data ? <Loading /> : audit.error ? <ErrorBox error={audit.error} onRetry={audit.reload} /> :
            <Timeline entries={[...(audit.data || [])].reverse()} />}
        </div>
      )}

      {scanRun && (
        <Scanner appId={app.id} appCode={app.code} initial={scanRun}
                 onDone={() => { setScanRun(null); refresh(); if (tab !== '') nav(`/applications/${app.id}`) }} />
      )}
      {outcomeOpen && <OutcomeModal app={app} onClose={() => setOutcomeOpen(false)} onSaved={() => { setOutcomeOpen(false); refresh() }} />}
    </div>
  )
}
