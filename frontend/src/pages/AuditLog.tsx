import { api, type AuditEntry } from '../api'
import Timeline from '../components/Timeline'
import { ErrorBox, Loading } from '../components/ui'
import { useApi } from '../util'

export default function AuditLogPage() {
  const { data, error, loading, reload } = useApi(() => api.get<AuditEntry[]>('/audit?limit=500'), [])
  return (
    <div className="page fade-up">
      <div className="eyebrow">Governance</div>
      <h1 className="title">System audit log</h1>
      <p className="muted" style={{ marginTop: 4, marginBottom: 24 }}>Sign-ins, document handling, rule changes, verification attempts and officer decisions across all applications.</p>
      {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <Loading /> : <Timeline entries={data || []} showApp />}
    </div>
  )
}
