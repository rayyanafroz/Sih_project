import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type ApplicationDetail, type ApplicationSummary } from '../api'
import { Badge, Button, Empty, ErrorBox, Loading, Modal } from '../components/ui'
import { useSession } from '../context'
import { fmtDate, useApi } from '../util'

interface Institution { id: number; aicte_id: string; name: string; address: string; state: string }

function NewApplicationModal({ onClose }: { onClose: () => void }) {
  const { meta, toast } = useSession()
  const nav = useNavigate()
  const insts = useApi(() => api.get<Institution[]>('/institutions'), [])
  const [institutionId, setInstitutionId] = useState<number | ''>('')
  const [category, setCategory] = useState('EOA')
  const [year, setYear] = useState('2026-27')
  const [area, setArea] = useState('')
  const [programmes, setProgrammes] = useState([{ programme: '', intake: '' }])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit() {
    setError(null)
    if (!institutionId) return setError('Select an institution')
    const progs = programmes.filter(p => p.programme.trim())
    if (!progs.length) return setError('Add at least one programme')
    setBusy(true)
    try {
      const app = await api.post<ApplicationDetail>('/applications', {
        institution_id: institutionId, category, academic_year: year,
        built_up_area_sqm: area ? Number(area) : null,
        programmes: progs.map(p => ({ programme: p.programme.trim(), intake: Number(p.intake || 0) })),
      })
      toast(`Application ${app.code} created`, 'success')
      nav(`/applications/${app.id}/documents`)
    } catch (e) {
      setError((e as Error).message)
    } finally { setBusy(false) }
  }

  const update = (i: number, key: 'programme' | 'intake', v: string) =>
    setProgrammes(ps => ps.map((p, j) => (j === i ? { ...p, [key]: v } : p)))

  return (
    <Modal title="New application" onClose={onClose} wide footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <Button busy={busy} onClick={submit}>Create application</Button>
    </>}>
      <p className="muted">Records the application as submitted by the institution. Documents are uploaded next.</p>
      <div className="grid2">
        <div className="field">
          <label>Institution</label>
          <select className="select" value={institutionId} onChange={e => setInstitutionId(Number(e.target.value) || '')}>
            <option value="">Select…</option>
            {insts.data?.map(i => <option key={i.id} value={i.id}>{i.name} ({i.aicte_id})</option>)}
          </select>
        </div>
        <div className="field">
          <label>Application category</label>
          <select className="select" value={category} onChange={e => setCategory(e.target.value)}>
            {meta?.settings.categories.map(c => <option key={c.code} value={c.code}>{c.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Academic year</label>
          <input className="input" value={year} onChange={e => setYear(e.target.value)} placeholder="2026-27" />
        </div>
        <div className="field">
          <label>Built-up area (sq.m)</label>
          <input className="input" type="number" min={0} value={area} onChange={e => setArea(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>Programmes and requested intake</label>
        <div className="stack" style={{ gap: 8 }}>
          {programmes.map((p, i) => (
            <div key={i} className="row">
              <input className="input" placeholder="e.g. B.Tech Computer Science and Engineering" value={p.programme}
                     onChange={e => update(i, 'programme', e.target.value)} />
              <input className="input" style={{ width: 110 }} type="number" min={0} placeholder="Intake" value={p.intake}
                     onChange={e => update(i, 'intake', e.target.value)} />
              <button className="btn btn-ghost" aria-label="Remove programme" disabled={programmes.length === 1}
                      onClick={() => setProgrammes(ps => ps.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <button className="btn btn-secondary btn-sm" style={{ alignSelf: 'flex-start' }}
                  onClick={() => setProgrammes(ps => [...ps, { programme: '', intake: '' }])}>+ Add programme</button>
        </div>
      </div>
      {error && <ErrorBox error={error} />}
    </Modal>
  )
}

export default function ApplicationsPage() {
  const { can, meta } = useSession()
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [creating, setCreating] = useState(false)
  const { data, error, loading, reload } = useApi(
    () => api.get<ApplicationSummary[]>(`/applications?q=${encodeURIComponent(q)}&status=${status}`), [q, status])

  return (
    <div className="page fade-up">
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <div>
          <div className="eyebrow">Applications</div>
          <h1 className="title">Application register</h1>
        </div>
        <span className="spacer" />
        {can('application:create') && <button className="btn btn-primary" onClick={() => setCreating(true)}>New application</button>}
      </div>
      <div className="row wrap" style={{ marginTop: 24 }}>
        <input className="input" style={{ maxWidth: 340 }} placeholder="Search by application, institution or AICTE ID…"
               value={q} onChange={e => setQ(e.target.value)} />
        <select className="select" style={{ maxWidth: 240 }} value={status} onChange={e => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          {Object.entries(meta?.status_labels || {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <div style={{ marginTop: 16 }}>
        {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <Loading /> : !data?.length ? (
          <Empty>No applications match.</Empty>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Application</th><th>Institution</th><th>Category</th><th>Year</th><th>Submitted</th><th>Status</th><th style={{ textAlign: 'right' }}>Open findings</th></tr></thead>
              <tbody>
                {data.map(a => (
                  <tr key={a.id} className="clickable" onClick={() => nav(`/applications/${a.id}`)}>
                    <td className="nums" style={{ fontWeight: 500 }}>{a.code}</td>
                    <td><div>{a.institution.name}</div><div className="faint" style={{ fontSize: 12 }}>{a.institution.aicte_id} · {a.institution.state}</div></td>
                    <td className="muted">{a.category_label}</td>
                    <td className="muted nums">{a.academic_year}</td>
                    <td className="muted nums">{fmtDate(a.submitted_at)}</td>
                    <td><Badge value={a.status} /></td>
                    <td className="nums" style={{ textAlign: 'right', fontWeight: a.open_findings ? 600 : 400, color: a.open_critical ? 'var(--accent)' : undefined }}>
                      {a.open_findings}{a.open_critical ? ` (${a.open_critical} critical)` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {creating && <NewApplicationModal onClose={() => setCreating(false)} />}
    </div>
  )
}
