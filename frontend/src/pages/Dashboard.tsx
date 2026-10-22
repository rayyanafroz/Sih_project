import { Link, useNavigate } from 'react-router-dom'
import { api, type Alert, type ApplicationSummary, type AuditEntry } from '../api'
import { Badge, Empty, ErrorBox, Loading } from '../components/ui'
import { useSession } from '../context'
import { fmtDate, fmtDateTime, useApi } from '../util'

interface DashboardData {
  metrics: { applications: number; needs_review: number; critical_findings: number; verification_pending: number; ready_for_decision: number }
  applications: ApplicationSummary[]
  alerts: Alert[]
  alert_count: number
  activity: AuditEntry[]
}

function greeting() {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

export default function DashboardPage() {
  const { user, meta } = useSession()
  const nav = useNavigate()
  const { data, error, loading, reload } = useApi(() => api.get<DashboardData>('/dashboard'), [])

  if (loading && !data) return <div className="page"><Loading /></div>
  if (error || !data) return <div className="page"><ErrorBox error={error || 'Failed to load'} onRetry={reload} /></div>
  const m = data.metrics
  const metrics = [
    { v: m.applications, l: 'Applications' },
    { v: m.needs_review, l: 'Awaiting review' },
    { v: m.critical_findings, l: 'Open critical findings', tone: m.critical_findings ? 'var(--accent)' : undefined },
    { v: m.verification_pending, l: 'Verification pending' },
    { v: m.ready_for_decision, l: 'Ready for decision' },
  ]

  return (
    <div className="page fade-up">
      <div className="muted">{greeting()}, {user?.name}</div>
      <h1 className="title">Application scrutiny overview</h1>
      <div className="faint" style={{ marginTop: 2 }}>
        Evaluation date {fmtDate(meta?.effective_reference_date)} · {user?.role_label}
      </div>

      <div className="metric-grid five" style={{ marginTop: 28 }}>
        {metrics.map(x => (
          <div key={x.l} className="metric-cell">
            <div className="metric-value" style={{ color: x.tone }}>{x.v}</div>
            <div className="metric-label">{x.l}</div>
          </div>
        ))}
      </div>

      <div className="section dash-grid">
        <div>
          <div className="section-head">
            <h3>Applications</h3>
            <Link to="/applications">View all →</Link>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Application</th><th>Institution</th><th>Status</th><th style={{ textAlign: 'right' }}>Open</th></tr></thead>
              <tbody>
                {data.applications.map(a => (
                  <tr key={a.id} className="clickable" onClick={() => nav(`/applications/${a.id}`)}>
                    <td className="nums" style={{ fontWeight: 500 }}>{a.code}</td>
                    <td className="muted">{a.institution.name}</td>
                    <td><Badge value={a.status} /></td>
                    <td className="nums" style={{ textAlign: 'right', fontWeight: a.open_findings ? 600 : 400, color: a.open_critical ? 'var(--accent)' : undefined }}>
                      {a.open_findings}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div>
          <div className="section-head">
            <h3>Alerts <span className="tab-count alert" style={{ marginLeft: 6 }}>{data.alert_count}</span></h3>
            <span className="faint" style={{ fontSize: 12 }}>Generated automatically from open findings</span>
          </div>
          {data.alerts.length === 0 ? <Empty>No open alerts.</Empty> : (
            <div className="card flush">
              {data.alerts.map((a, i) => (
                <Link key={i} to={`/applications/${a.application_id}${a.finding_id ? `?finding=${a.finding_id}` : '/verification'}`}
                      className="row" style={{ padding: '11px 16px', borderBottom: i < data.alerts.length - 1 ? '1px solid var(--border)' : undefined, color: 'inherit', alignItems: 'flex-start' }}>
                  <span className={`badge-dot`} style={{ marginTop: 7, color: a.severity === 'CRITICAL' ? 'var(--accent)' : a.severity === 'WARNING' ? 'var(--warning)' : 'var(--info)', width: 7, height: 7 }} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{a.message}</div>
                    <div className="faint" style={{ fontSize: 12 }}>{a.kind} · {a.application_code}</div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="section">
        <div className="section-head"><h3>Recent activity</h3></div>
        <div className="card flush">
          {data.activity.map((e, i) => (
            <div key={e.id} className="row" style={{ padding: '11px 18px', borderBottom: i < data.activity.length - 1 ? '1px solid var(--border)' : undefined }}>
              <span style={{ width: 7, height: 7, borderRadius: '50%', flexShrink: 0, background: e.actor_type === 'user' ? 'var(--accent)' : 'var(--border)' }} />
              <span className="faint nums" style={{ fontSize: 12, minWidth: 140 }}>{fmtDateTime(e.at)}</span>
              <span style={{ fontSize: 13 }}>{e.summary}</span>
              <span className="spacer" />
              {e.application_code && <span className="tag">{e.application_code}</span>}
              <span className="faint" style={{ fontSize: 12 }}>{e.actor}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
