import { Link, useParams } from 'react-router-dom'
import { api, type ApplicationDetail, type DocumentInfo, type Finding, type RuleResult, type Run, type User, type Verification } from '../api'
import { Badge, ErrorBox, Loading } from '../components/ui'
import { useSession } from '../context'
import { fieldLabel, fmtDate, fmtDateTime, humanize, useApi } from '../util'

interface Report {
  generated_at: string; generated_by: User; disclaimer: string; application: ApplicationDetail
  documents: DocumentInfo[]; compliance: { run: Run | null; results: RuleResult[] }; findings: Finding[]; verifications: Verification[]
}

export default function ReportPage() {
  const { id } = useParams()
  const { docTypeLabel } = useSession()
  const { data, error, loading, reload } = useApi(() => api.get<Report>(`/applications/${id}/report`), [id])
  if (loading && !data) return <div className="page"><Loading /></div>
  if (error || !data) return <div className="page"><ErrorBox error={error || 'Failed'} onRetry={reload} /></div>
  const a = data.application
  const docName = (docId: number) => data.documents.find(d => d.id === docId)?.filename || `#${docId}`

  function download() {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${a.code}-validation-report.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="no-print row" style={{ padding: '14px 24px', borderBottom: '1px solid var(--border)', background: 'var(--surface)' }}>
        <Link to={`/applications/${a.id}`}>← Back to {a.code}</Link>
        <span className="spacer" />
        <button className="btn btn-secondary btn-sm" onClick={download}>Download JSON</button>
        <button className="btn btn-primary btn-sm" onClick={() => window.print()}>Print / save as PDF</button>
      </div>
      <div className="report">
        <div className="eyebrow">AICTE VerifyAI · Structured validation report</div>
        <h2>{a.code} — {a.institution.name}</h2>
        <p className="muted">{a.category_label} · Academic year {a.academic_year} · AICTE ID {a.institution.aicte_id}</p>
        <p className="faint" style={{ fontSize: 12 }}>Generated {fmtDateTime(data.generated_at)} by {data.generated_by.name} ({data.generated_by.role_label})
          {data.compliance.run && <> · based on pre-scrutiny run #{data.compliance.run.id} with evaluation date {fmtDate(data.compliance.run.reference_date)}</>}</p>
        <div className="disclaimer" style={{ marginTop: 12 }}>{data.disclaimer}</div>

        <h3>Summary</h3>
        <table><tbody>
          <tr><th>Status</th><td>{a.status_label}</td><th>Officer outcome</th><td>{a.outcome ? `${humanize(a.outcome)} — ${a.outcome_by?.name}, ${fmtDateTime(a.outcome_at)}` : 'Not yet recorded'}</td></tr>
          <tr><th>Documents</th><td>{a.documents.processed}/{a.documents.total} processed</td><th>Rules passed</th><td>{a.rules.passed}/{a.rules.evaluated}</td></tr>
          <tr><th>Sources verified</th><td>{a.verification.verified}/{a.verification.total}</td><th>Open findings</th><td>{a.findings.critical} critical, {a.findings.warning} warning, {a.findings.info} pending</td></tr>
        </tbody></table>
        {a.outcome_note && <p style={{ marginTop: 8 }}><b>Officer reasoning:</b> {a.outcome_note}</p>}

        <h3>Findings</h3>
        <table>
          <thead><tr><th>Severity</th><th>Finding</th><th>Expected / observed</th><th>Evidence</th><th>Status</th></tr></thead>
          <tbody>
            {data.findings.map(f => (
              <tr key={f.id}>
                <td><Badge value={f.severity} /></td>
                <td><b>{f.title}</b><div className="muted">{f.description}</div><div className="faint">{f.rule_id} v{f.rule_version} · {f.recommended_action}</div></td>
                <td>{f.expected_value || '—'}<br />{f.actual_value || ''}</td>
                <td>{f.evidence.map((e, i) => <div key={i}>{e.kind === 'document' ? `${e.filename} p.${e.page}` : `${e.label}${e.value ? `: ${e.value}` : ''}`}</div>)}</td>
                <td>{humanize(f.status)}{f.resolution_note ? <div className="faint">{f.resolution_note}</div> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h3>Compliance checklist</h3>
        <table>
          <thead><tr><th>Rule</th><th>Requirement</th><th>Result</th><th>Detail</th></tr></thead>
          <tbody>
            {data.compliance.results.map(r => (
              <tr key={r.rule_id}><td className="mono">{r.rule_id} v{r.rule_version}</td><td>{r.rule_name}</td><td>{humanize(r.outcome)}</td><td>{r.message}</td></tr>
            ))}
          </tbody>
        </table>

        <h3>Source verification</h3>
        <table>
          <thead><tr><th>Document</th><th>Source</th><th>Method</th><th>Status</th><th>Timestamp</th></tr></thead>
          <tbody>
            {data.verifications.map(v => (
              <tr key={v.id}><td>{docName(v.document_id)}</td><td>{v.source_name}</td><td>{v.method}</td><td>{humanize(v.status)}</td><td>{fmtDateTime(v.responded_at || v.requested_at)}</td></tr>
            ))}
          </tbody>
        </table>

        <h3>Documents and extracted data</h3>
        {data.documents.map(d => (
          <div key={d.id} style={{ marginBottom: 12 }}>
            <b>{d.filename}</b> <span className="muted">— {docTypeLabel(d.effective_type)} · {d.text_method === 'ocr' ? `OCR ${d.ocr_confidence}%` : 'text layer'} · SHA-256 {d.sha256.slice(0, 16)}…</span>
            {d.fields && d.fields.length > 0 && (
              <table style={{ marginTop: 4 }}><tbody>
                {d.fields.map(f => <tr key={f.id}><td style={{ width: '35%' }}>{fieldLabel(f.field)}</td><td>{f.value}</td><td style={{ width: 70 }}>p.{f.page}</td><td style={{ width: 60 }}>{Math.round(f.confidence * 100)}%</td></tr>)}
              </tbody></table>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
