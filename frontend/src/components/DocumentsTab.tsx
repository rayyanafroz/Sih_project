import { useRef, useState } from 'react'
import { api, fileUrl, uploadWithProgress, type ApplicationDetail, type DocumentInfo, type ExtractedField } from '../api'
import { useSession } from '../context'
import { fieldLabel, fmtDateTime, fmtSize, useApi } from '../util'
import { Badge, Button, DocIcon, Empty, ErrorBox, Loading, NeedsRole } from './ui'

interface Staged { key: string; file: File; type: string; progress: number; state: 'staged' | 'uploading' | 'done' | 'error'; error?: string }

function useTypeGuess() {
  const { meta } = useSession()
  return (filename: string): string => {
    const name = filename.toLowerCase().replace(/[^a-z0-9]+/g, ' ')
    for (const t of meta?.document_types || []) {
      for (const hint of t.filename_hints) {
        if (new RegExp(`\\b${hint.toLowerCase().replace(/[^a-z0-9 ]/g, ' ')}`).test(name)) return t.code
      }
    }
    return ''
  }
}

function Uploader({ app, onUploaded }: { app: ApplicationDetail; onUploaded: () => void }) {
  const { meta, toast } = useSession()
  const guess = useTypeGuess()
  const [staged, setStaged] = useState<Staged[]>([])
  const [over, setOver] = useState(false)
  const [busy, setBusy] = useState(false)
  const [demoBusy, setDemoBusy] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const allowed = meta?.settings.allowed_extensions || ['pdf', 'png', 'jpg', 'jpeg']
  const maxMb = meta?.settings.max_upload_mb || 15

  function add(files: FileList | null) {
    if (!files) return
    const next: Staged[] = []
    for (const file of Array.from(files)) {
      const ext = file.name.split('.').pop()?.toLowerCase() || ''
      const error = !allowed.includes(ext) ? `.${ext} files are not allowed` : file.size > maxMb * 1024 * 1024 ? `Larger than ${maxMb} MB` : undefined
      next.push({ key: `${file.name}-${file.size}-${Math.random()}`, file, type: guess(file.name), progress: 0, state: error ? 'error' : 'staged', error })
    }
    setStaged(s => [...s.filter(x => x.state !== 'done'), ...next])
  }

  async function uploadAll() {
    setBusy(true)
    let ok = 0
    for (const item of staged) {
      if (item.state !== 'staged') continue
      setStaged(s => s.map(x => (x.key === item.key ? { ...x, state: 'uploading' } : x)))
      const form = new FormData()
      form.append('files', item.file)
      form.append('declared_types', item.type)
      try {
        await uploadWithProgress(`/applications/${app.id}/documents`, form,
          pct => setStaged(s => s.map(x => (x.key === item.key ? { ...x, progress: pct } : x))))
        setStaged(s => s.map(x => (x.key === item.key ? { ...x, state: 'done', progress: 100 } : x)))
        ok++
      } catch (e) {
        setStaged(s => s.map(x => (x.key === item.key ? { ...x, state: 'error', error: (e as Error).message } : x)))
      }
    }
    setBusy(false)
    if (ok) { toast(`${ok} document(s) uploaded`, 'success'); onUploaded() }
  }

  async function loadDemo() {
    setDemoBusy(true)
    try {
      const docs = await api.post<DocumentInfo[]>(`/applications/${app.id}/demo-documents`)
      toast(docs.length ? `${docs.length} synthetic demo document(s) attached` : 'Demo documents are already attached', 'success')
      onUploaded()
    } catch (e) { toast((e as Error).message, 'error') } finally { setDemoBusy(false) }
  }

  const pending = staged.filter(s => s.state === 'staged').length
  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div
        className={`dropzone ${over ? 'over' : ''}`} role="button" tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') input.current?.click() }}
        onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}>
        <div style={{ fontWeight: 600 }}>Drop documents here or click to browse</div>
        <div className="help" style={{ marginTop: 4 }}>{allowed.map(a => a.toUpperCase()).join(', ')} · up to {maxMb} MB each · multiple files allowed · scanned documents are read with OCR</div>
        <input ref={input} type="file" multiple hidden accept={allowed.map(a => `.${a}`).join(',')}
               onChange={e => { add(e.target.files); e.target.value = '' }} />
      </div>
      {staged.length > 0 && (
        <div className="stack" style={{ marginTop: 14, gap: 8 }}>
          {staged.map(s => (
            <div key={s.key} className="row" style={{ gap: 10 }}>
              <DocIcon />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="row" style={{ gap: 8 }}>
                  <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.file.name}</span>
                  <span className="faint" style={{ fontSize: 12 }}>{fmtSize(s.file.size)}</span>
                </div>
                {s.state === 'error' ? <div className="help" style={{ color: 'var(--accent)' }}>{s.error}</div>
                  : s.state !== 'staged' ? <div className={`progress ${s.state === 'done' ? 'done' : ''}`} style={{ marginTop: 6 }}><div style={{ width: `${s.progress}%` }} /></div> : null}
              </div>
              <select className="select" style={{ width: 240 }} value={s.type} disabled={s.state !== 'staged'}
                      onChange={e => setStaged(x => x.map(y => (y.key === s.key ? { ...y, type: e.target.value } : y)))}
                      aria-label={`Document type for ${s.file.name}`}>
                <option value="">Auto-detect from content</option>
                {meta?.document_types.map(t => <option key={t.code} value={t.code}>{t.label}</option>)}
              </select>
              {s.state === 'done' ? <Badge value="VERIFIED" label="Uploaded" /> :
                <button className="btn btn-ghost btn-sm" disabled={s.state === 'uploading'} aria-label="Remove from list"
                        onClick={() => setStaged(x => x.filter(y => y.key !== s.key))}>×</button>}
            </div>
          ))}
          <div className="row">
            <span className="spacer" />
            <button className="btn btn-ghost btn-sm" onClick={() => setStaged([])} disabled={busy}>Clear list</button>
            <Button busy={busy} disabled={!pending} onClick={uploadAll}>{pending ? `Upload ${pending} file${pending === 1 ? '' : 's'}` : 'Upload'}</Button>
          </div>
        </div>
      )}
      {app.demo_documents_available && (
        <div className="row" style={{ marginTop: 12 }}>
          <span className="help">Demo shortcut: attach this application's synthetic test documents through the same upload pipeline.</span>
          <span className="spacer" />
          <Button className="btn-secondary btn-sm" busy={demoBusy} onClick={loadDemo}>Load synthetic demo documents</Button>
        </div>
      )}
    </div>
  )
}

function DocumentDetail({ docId, app, onChanged }: { docId: number; app: ApplicationDetail; onChanged: () => void }) {
  const { can, toast, docTypeLabel } = useSession()
  const { data: d, error, loading, reload } = useApi(() => api.get<DocumentInfo>(`/documents/${docId}`), [docId])
  const [page, setPage] = useState(1)
  const [field, setField] = useState<ExtractedField | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const replaceInput = useRef<HTMLInputElement>(null)

  if (loading && !d) return <div className="card" style={{ marginTop: 20 }}><Loading /></div>
  if (error || !d) return <ErrorBox error={error || 'Failed to load'} onRetry={reload} />
  const editable = can('document:upload') && !app.outcome && app.status !== 'PROCESSING'
  const boxes: Record<string, string> = field?.bbox && field.page === page ? { boxes: field.bbox.join(',') } : {}
  const pageCount = Math.max(d.page_count, 1)

  async function replace(file: File | undefined) {
    if (!file) return
    setBusy('replace')
    const form = new FormData()
    form.append('file', file)
    try {
      await uploadWithProgress(`/documents/${docId}/replace`, form, () => {})
      toast(`${d!.filename} replaced — re-run pre-scrutiny to update findings`, 'success')
      onChanged()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }
  async function remove() {
    if (!window.confirm(`Remove ${d!.filename} from this submission? It stays in the audit trail.`)) return
    setBusy('remove')
    try { await api.del(`/documents/${docId}`); toast('Document removed', 'success'); onChanged() }
    catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }
  async function reprocess() {
    setBusy('process')
    try { await api.post(`/documents/${docId}/process`); toast('Document re-processed', 'success'); reload(); onChanged() }
    catch (e) { toast((e as Error).message, 'error') } finally { setBusy(null) }
  }

  return (
    <div className="evidence-split fade-up" style={{ marginTop: 20 }}>
      <div className="evidence-doc">
        <div className="row" style={{ fontSize: 12 }}>
          <DocIcon /><b>{d.filename}</b>
          <span className="spacer" />
          {pageCount > 1 && (
            <div className="row" style={{ gap: 6 }}>
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>‹</button>
              <span className="nums">Page {page} / {pageCount}</span>
              <button className="btn btn-ghost btn-sm" disabled={page >= pageCount} onClick={() => setPage(p => p + 1)}>›</button>
            </div>
          )}
          <a href={fileUrl(`/documents/${d.id}/file`)} target="_blank" rel="noreferrer">Open original ↗</a>
        </div>
        <div className="evidence-img-wrap">
          <img src={fileUrl(`/documents/${d.id}/pages/${page}/image`, boxes)} alt={`${d.filename} page ${page}`} />
        </div>
        <div className="help">Click an extracted field to highlight where it was read from.</div>
      </div>
      <div className="evidence-detail">
        <div>
          <div className="card-title" style={{ marginBottom: 6 }}>Document intelligence</div>
          <h3>{docTypeLabel(d.effective_type)}</h3>
          <div className="row wrap" style={{ marginTop: 8 }}>
            <Badge value={d.status} />
            {d.text_method && <span className="tag">{d.text_method === 'ocr' ? `OCR · ${d.ocr_confidence ?? '—'}% confidence` : d.text_method === 'text' ? 'Text layer' : d.text_method === 'none' ? 'No readable text' : 'Text + OCR'}</span>}
            {d.classification_confidence !== null && d.detected_type && <span className="tag">Classifier {Math.round(d.classification_confidence * 100)}%</span>}
          </div>
          {d.declared_type && d.detected_type && d.declared_type !== d.detected_type && (
            <div className="banner tone-warning" style={{ marginTop: 10 }}>Uploaded as {docTypeLabel(d.declared_type)}, content reads as {docTypeLabel(d.detected_type)}.</div>
          )}
          {d.error && <div className="error-box" style={{ marginTop: 10 }}>{d.error}</div>}
        </div>
        <div>
          <h4 style={{ marginBottom: 8 }}>Extracted fields {d.fields?.length ? `(${d.fields.length})` : ''}</h4>
          {d.status === 'UPLOADED' ? <p className="help">Not processed yet — run AI pre-scrutiny.</p> : !d.fields?.length ? <p className="help">No structured fields found.</p> : (
            <div className="table-wrap">
              <table className="table" style={{ fontSize: 13 }}>
                <thead><tr><th>Field</th><th>Value</th><th>Page</th><th>Conf.</th></tr></thead>
                <tbody>
                  {d.fields.map(f => (
                    <tr key={f.id} className={`clickable ${field?.id === f.id ? 'selected' : ''}`}
                        onClick={() => { setField(f); if (f.page) setPage(f.page) }}>
                      <td className="muted">{fieldLabel(f.field)}</td>
                      <td style={{ fontWeight: 500, overflowWrap: 'anywhere' }}>{f.value}</td>
                      <td className="nums">{f.page}</td>
                      <td className="nums">{Math.round(f.confidence * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <div className="flag-box">
          <div className="flag-row"><span className="flag-label">SHA-256</span><span className="flag-value mono">{d.sha256.slice(0, 24)}…</span></div>
          <div className="flag-row"><span className="flag-label">Size / pages</span><span className="flag-value">{fmtSize(d.size)} · {d.page_count || '—'} page(s)</span></div>
          <div className="flag-row"><span className="flag-label">Uploaded</span><span className="flag-value">{fmtDateTime(d.uploaded_at)}</span></div>
          {d.metadata?.producer && <div className="flag-row"><span className="flag-label">PDF producer</span><span className="flag-value">{d.metadata.producer}</span></div>}
          {d.metadata?.modDate && <div className="flag-row"><span className="flag-label">Created / modified</span><span className="flag-value mono">{d.metadata.creationDate?.slice(2, 10)} / {d.metadata.modDate?.slice(2, 10)}</span></div>}
          {d.replaces_document_id && <div className="flag-row"><span className="flag-label">Replaces</span><span className="flag-value">document #{d.replaces_document_id}</span></div>}
        </div>
        {editable ? (
          <div className="row wrap">
            <Button className="btn-secondary btn-sm" busy={busy === 'replace'} onClick={() => replaceInput.current?.click()}>Replace with corrected file</Button>
            <Button className="btn-secondary btn-sm" busy={busy === 'process'} onClick={reprocess}>Re-process</Button>
            <Button className="btn-danger btn-sm" busy={busy === 'remove'} onClick={remove}>Remove</Button>
            <input ref={replaceInput} type="file" hidden accept=".pdf,.png,.jpg,.jpeg" onChange={e => { replace(e.target.files?.[0]); e.target.value = '' }} />
          </div>
        ) : !can('document:upload') ? <NeedsRole role="Scrutiny Officer" /> : null}
      </div>
    </div>
  )
}

export default function DocumentsTab({ app, version, onChanged }: { app: ApplicationDetail; version: number; onChanged: () => void }) {
  const { can, docTypeLabel } = useSession()
  const { data, error, loading, reload } = useApi(() => api.get<DocumentInfo[]>(`/applications/${app.id}/documents`), [app.id, version])
  const [selected, setSelected] = useState<number | null>(null)
  const changed = () => { reload(true); onChanged() }
  const canUpload = can('document:upload') && !app.outcome && app.status !== 'PROCESSING'

  return (
    <div style={{ marginTop: 20 }}>
      {canUpload && <Uploader app={app} onUploaded={changed} />}
      {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <Loading /> : !data?.length ? (
        <Empty>No documents yet.{canUpload ? ' Drop files above to begin.' : ''}</Empty>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Document</th><th>Type</th><th>Status</th><th>Read via</th><th style={{ textAlign: 'right' }}>Fields</th><th>Verification</th></tr></thead>
            <tbody>
              {data.map(d => (
                <tr key={d.id} className={`clickable ${selected === d.id ? 'selected' : ''}`} onClick={() => setSelected(selected === d.id ? null : d.id)}>
                  <td><div className="row" style={{ gap: 8 }}><DocIcon /><span style={{ fontWeight: 500 }}>{d.filename}</span></div>
                    <div className="faint" style={{ fontSize: 12, marginLeft: 22 }}>{fmtSize(d.size)} · {fmtDateTime(d.uploaded_at)}</div></td>
                  <td>{docTypeLabel(d.effective_type)}{d.declared_type && d.detected_type && d.declared_type !== d.detected_type && <div className="help" style={{ color: 'var(--warning)' }}>declared: {docTypeLabel(d.declared_type)}</div>}</td>
                  <td><Badge value={d.status} /></td>
                  <td className="muted">{d.text_method === 'ocr' ? `OCR (${d.ocr_confidence ?? '—'}%)` : d.text_method === 'text' ? 'Text layer' : d.text_method === 'none' ? 'No text' : d.text_method || '—'}</td>
                  <td className="nums" style={{ textAlign: 'right' }}>{d.status === 'PROCESSED' ? d.field_count : '—'}</td>
                  <td>{d.verification ? <Badge value={d.verification.status} /> : <span className="faint">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selected && data?.some(d => d.id === selected) && <DocumentDetail key={selected} docId={selected} app={app} onChanged={changed} />}
    </div>
  )
}
