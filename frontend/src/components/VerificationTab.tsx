import { useState } from 'react'
import { api, type ApplicationDetail, type DocumentInfo, type Verification } from '../api'
import { useSession } from '../context'
import { fmtDateTime, useApi } from '../util'
import { Badge, Button, Empty, ErrorBox, Loading, MockTag, Modal, NeedsRole } from './ui'

interface Row { document: DocumentInfo; latest: Verification | null; history: Verification[] }

function ManualModal({ doc, onClose, onSaved }: { doc: DocumentInfo; onClose: () => void; onSaved: () => void }) {
  const { toast } = useSession()
  const [status, setStatus] = useState('VERIFIED')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function save() {
    setBusy(true)
    setError(null)
    try {
      await api.post(`/documents/${doc.id}/verify/manual`, { status, note })
      toast('Manual verification recorded; rules re-applied', 'success')
      onSaved()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Record manual confirmation — ${doc.filename}`} onClose={onClose} footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <Button busy={busy} disabled={note.trim().length < 5} onClick={save}>Record confirmation</Button>
    </>}>
      <p className="muted">Use when automated verification is unavailable or inconclusive. Your name, the result and the note are stored in the audit trail.</p>
      <div className="field">
        <label>Result</label>
        <select className="select" value={status} onChange={e => setStatus(e.target.value)}>
          <option value="VERIFIED">Verified with issuing authority</option>
          <option value="MISMATCH">Mismatch detected</option>
          <option value="EXPIRED">Expired per issuing authority</option>
          <option value="MANUAL_REVIEW">Still unresolved — keep under manual review</option>
        </select>
      </div>
      <div className="field">
        <label>How was it confirmed? (required)</label>
        <textarea className="textarea" value={note} onChange={e => setNote(e.target.value)}
                  placeholder="e.g. Confirmed by phone with the issuing office; registry entry read back and matched." />
      </div>
      {error && <ErrorBox error={error} />}
    </Modal>
  )
}

export default function VerificationTab({ app, version, onChanged }: { app: ApplicationDetail; version: number; onChanged: () => void }) {
  const { can, toast, docTypeLabel } = useSession()
  const { data, error, loading, reload } = useApi(() => api.get<Row[]>(`/applications/${app.id}/verifications`), [app.id, version])
  const [busy, setBusy] = useState<number | null>(null)
  const [manualDoc, setManualDoc] = useState<DocumentInfo | null>(null)
  const canRun = can('verification:run') && !app.outcome && app.status !== 'PROCESSING'

  async function run(fn: () => Promise<Verification>, id: number) {
    setBusy(id)
    try {
      const v = await fn()
      toast(`Verification: ${v.status.replace(/_/g, ' ').toLowerCase()}`, v.status === 'VERIFIED' ? 'success' : 'info')
      reload(true)
      onChanged()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }

  if (loading && !data) return <Loading />
  if (error) return <ErrorBox error={error} onRetry={reload} />
  const rows = (data || []).filter(r => r.latest)
  const unverified = (data || []).filter(r => !r.latest && r.document.status === 'PROCESSED')

  return (
    <div style={{ marginTop: 20 }}>
      <div className="row" style={{ marginBottom: 16 }}>
        <p className="muted">Submitted details are compared with records returned by the issuing authority. Every attempt stores source, method, timestamp and response.</p>
        <span className="spacer" />
        {!can('verification:run') && <NeedsRole role="Verification Officer" />}
      </div>
      {rows.length === 0 && <Empty>No verification requests yet. They are sent automatically during AI pre-scrutiny.</Empty>}
      <div className="stack" style={{ gap: 14 }}>
        {rows.map(({ document: d, latest: v, history }) => v && (
          <div key={d.id} className={`verification-card st-${v.status}`}>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{v.query?.reference_number || d.filename}</div>
                <div className="muted" style={{ fontSize: 13 }}>{docTypeLabel(d.effective_type)} · {d.filename}</div>
              </div>
              <span className="spacer" />
              {v.is_mock && <MockTag />}
              <Badge value={v.status} />
            </div>
            <div className="verification-grid">
              <div><div className="kv-label">Source</div><div className="kv-value">{v.source_name}</div></div>
              <div><div className="kv-label">Method</div><div className="kv-value">{v.method}</div></div>
              <div><div className="kv-label">Requested</div><div className="kv-value">{fmtDateTime(v.requested_at)}<div className="faint" style={{ fontSize: 12 }}>by {v.requested_by}</div></div></div>
              <div><div className="kv-label">Response</div><div className="kv-value">{v.responded_at ? fmtDateTime(v.responded_at) : 'Awaiting'}</div></div>
            </div>
            <p style={{ marginTop: 12 }}>{v.message}</p>
            {v.comparison?.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 12 }}>
                <table className="table" style={{ fontSize: 13 }}>
                  <thead><tr><th>Field</th><th>Submitted document</th><th>Official record</th><th>Match</th></tr></thead>
                  <tbody>
                    {v.comparison.map(c => (
                      <tr key={c.field}>
                        <td className="muted">{c.label}</td><td>{c.submitted}</td><td>{c.official}</td>
                        <td>{c.match ? <Badge value="VERIFIED" label="Match" /> : <Badge value="MISMATCH" label="Differs" />}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="row wrap" style={{ marginTop: 14 }}>
              {history.length > 1 && <span className="help">{history.length} attempts recorded</span>}
              <span className="spacer" />
              {canRun && (v.status === 'PENDING' || v.status === 'SOURCE_UNAVAILABLE') && (
                <Button className="btn-secondary btn-sm" busy={busy === v.id} onClick={() => run(() => api.post<Verification>(`/verifications/${v.id}/refresh`), v.id)}>
                  {v.status === 'PENDING' ? 'Check for response' : 'Retry source'}
                </Button>
              )}
              {canRun && <Button className="btn-secondary btn-sm" busy={busy === -d.id} onClick={() => run(() => api.post<Verification>(`/documents/${d.id}/verify`), -d.id)}>Verify again</Button>}
              {canRun && v.status !== 'VERIFIED' && <Button className="btn-sm" onClick={() => setManualDoc(d)}>Record manual confirmation</Button>}
            </div>
          </div>
        ))}
      </div>
      {unverified.length > 0 && (
        <div className="section">
          <h4 style={{ marginBottom: 8 }}>Documents without a verification request</h4>
          <div className="card flush">
            {unverified.map(({ document: d }, i) => (
              <div key={d.id} className="row" style={{ padding: '10px 16px', borderBottom: i < unverified.length - 1 ? '1px solid var(--border)' : undefined }}>
                <span>{d.filename}</span><span className="faint">· {docTypeLabel(d.effective_type)}</span>
                <span className="spacer" />
                {canRun && <Button className="btn-ghost btn-sm" busy={busy === -d.id} onClick={() => run(() => api.post<Verification>(`/documents/${d.id}/verify`), -d.id)}>Request verification</Button>}
              </div>
            ))}
          </div>
        </div>
      )}
      {manualDoc && <ManualModal doc={manualDoc} onClose={() => setManualDoc(null)} onSaved={() => { setManualDoc(null); reload(true); onChanged() }} />}
    </div>
  )
}
