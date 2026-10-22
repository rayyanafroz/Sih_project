import { useState } from 'react'
import { api, type Meta, type ParamSpec, type Rule } from '../api'
import { Badge, Button, ErrorBox, Loading, MockTag, Modal } from '../components/ui'
import { useSession } from '../context'
import { fmtDate, fmtDateTime, humanize, useApi } from '../util'

const GROUPS = ['DOCUMENT', 'EXPIRY', 'CONSISTENCY', 'REGULATORY', 'ANOMALY', 'VERIFICATION', 'INFRASTRUCTURE']

function ParamEditor({ spec, value, onChange, meta }: { spec: ParamSpec; value: unknown; onChange: (v: unknown) => void; meta: Meta }) {
  const types = meta.document_types
  if (spec.type === 'int' || spec.type === 'float') {
    return <input className="input" type="number" step={spec.type === 'float' ? 'any' : 1} value={value as number ?? ''}
                  onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))} />
  }
  if (spec.type === 'doc_type') {
    return (
      <select className="select" value={value as string ?? ''} onChange={e => onChange(e.target.value)}>
        <option value="">Select…</option>
        {types.map(t => <option key={t.code} value={t.code}>{t.label}</option>)}
      </select>
    )
  }
  if (spec.type === 'doc_types') {
    const sel = (value as string[]) || []
    return (
      <div className="row wrap" style={{ gap: '6px 14px' }}>
        {types.map(t => (
          <label key={t.code} className="checkbox">
            <input type="checkbox" checked={sel.includes(t.code)}
                   onChange={e => onChange(e.target.checked ? [...sel, t.code] : sel.filter(x => x !== t.code))} />
            {t.label}
          </label>
        ))}
      </div>
    )
  }
  if (spec.type === 'string_list') {
    return <input className="input" value={((value as string[]) || []).join(', ')}
                  onChange={e => onChange(e.target.value.split(',').map(s => s.trim()).filter(Boolean))} />
  }
  return <input className="input" value={value as string ?? ''} onChange={e => onChange(e.target.value)} />
}

function RuleModal({ rule, meta, onClose, onSaved }: { rule: Rule | null; meta: Meta; onClose: () => void; onSaved: () => void }) {
  const { toast } = useSession()
  const creating = !rule
  const detail = useApi(() => (rule ? api.get<Rule>(`/rules/${rule.rule_id}`) : Promise.resolve(null)), [rule?.rule_id])
  const [form, setForm] = useState(() => ({
    rule_id: rule?.rule_id || 'EOA-DOC-0', name: rule?.name || '', description: rule?.description || '',
    group: rule?.group || 'DOCUMENT', check: rule?.check || 'required_document', severity: rule?.severity || 'CRITICAL',
    applies_to: rule?.applies_to || ['EOA'], params: { ...(rule?.params || {}) } as Record<string, unknown>,
    source_reference: rule?.source_reference || '', enabled: rule?.enabled ?? true,
  }))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const check = meta.checks.find(c => c.name === form.check)
  const set = (k: string, v: unknown) => setForm(f => ({ ...f, [k]: v }))

  async function save() {
    setBusy(true)
    setError(null)
    try {
      if (creating) {
        await api.post('/rules', { ...form, change_note: note })
        toast(`Rule ${form.rule_id} created`, 'success')
      } else {
        const r = await api.put<Rule>(`/rules/${rule.rule_id}`, {
          name: form.name, description: form.description, severity: form.severity, applies_to: form.applies_to,
          params: form.params, source_reference: form.source_reference, enabled: form.enabled, change_note: note,
        })
        toast(`${r.rule_id} saved as version ${r.version}. Re-run pre-scrutiny to apply.`, 'success')
      }
      onSaved()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <Modal wide title={creating ? 'New rule' : `Edit ${rule.rule_id}`} onClose={onClose} footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <Button busy={busy} disabled={note.trim().length < 3 || !form.name} onClick={save}>{creating ? 'Create rule' : 'Save new version'}</Button>
    </>}>
      <div className="grid2">
        <div className="field"><label>Rule ID</label>
          <input className="input mono" value={form.rule_id} disabled={!creating} onChange={e => set('rule_id', e.target.value.toUpperCase())} /></div>
        <div className="field"><label>Name</label><input className="input" value={form.name} onChange={e => set('name', e.target.value)} /></div>
      </div>
      <div className="field"><label>Description</label>
        <textarea className="textarea" style={{ minHeight: 56 }} value={form.description} onChange={e => set('description', e.target.value)} /></div>
      <div className="grid2">
        <div className="field"><label>Check</label>
          <select className="select" value={form.check} disabled={!creating}
                  onChange={e => setForm(f => ({ ...f, check: e.target.value, params: {} }))}>
            {meta.checks.map(c => <option key={c.name} value={c.name}>{c.label}</option>)}
          </select>
          {check && <span className="help">{check.description}</span>}
        </div>
        <div className="grid2">
          <div className="field"><label>Severity</label>
            <select className="select" value={form.severity} onChange={e => set('severity', e.target.value)}>
              <option value="CRITICAL">Critical</option><option value="WARNING">Warning</option><option value="INFO">Info</option>
            </select></div>
          <div className="field"><label>Group</label>
            <select className="select" value={form.group} disabled={!creating} onChange={e => set('group', e.target.value)}>
              {GROUPS.map(g => <option key={g} value={g}>{humanize(g)}</option>)}
            </select></div>
        </div>
      </div>
      {check && check.params.length > 0 && (
        <div className="card" style={{ background: 'var(--paper)' }}>
          <div className="card-title">Parameters</div>
          <div className="stack">
            {check.params.map(p => (
              <div key={p.name} className="field">
                <label>{p.label} <span className="faint">(default: {Array.isArray(p.default) ? (p.default as string[]).join(', ') || 'none' : String(p.default)})</span></label>
                <ParamEditor spec={p} meta={meta} value={form.params[p.name] ?? p.default} onChange={v => set('params', { ...form.params, [p.name]: v })} />
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="field"><label>Applies to application categories</label>
        <div className="row wrap">
          {meta.settings.categories.map(c => (
            <label key={c.code} className="checkbox">
              <input type="checkbox" checked={form.applies_to.includes(c.code)}
                     onChange={e => set('applies_to', e.target.checked ? [...form.applies_to, c.code] : form.applies_to.filter(x => x !== c.code))} />
              {c.label}
            </label>
          ))}
        </div>
      </div>
      <div className="grid2">
        <div className="field"><label>Regulatory source / reference</label>
          <input className="input" value={form.source_reference} onChange={e => set('source_reference', e.target.value)} placeholder="e.g. APH 2026-27, clause …" /></div>
        {!creating && <label className="checkbox" style={{ marginTop: 22 }}><input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)} />Rule enabled</label>}
      </div>
      <div className="field"><label>Reason for change (required — recorded with the new version)</label>
        <input className="input" value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. Updated per circular dated …" /></div>
      {error && <ErrorBox error={error} />}
      {!creating && detail.data?.history && (
        <div>
          <h4 style={{ marginBottom: 8 }}>Version history</h4>
          <div className="history">
            {detail.data.history.map(h => (
              <div key={h.version} className="history-item">
                <b>v{h.version}</b> <span className="faint">· {h.changed_by} · {fmtDateTime(h.changed_at)}</span>
                <div className="muted">{h.change_note}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </Modal>
  )
}

function ToggleModal({ rule, onClose, onSaved }: { rule: Rule; onClose: () => void; onSaved: () => void }) {
  const { toast } = useSession()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  async function save() {
    setBusy(true)
    try {
      await api.put(`/rules/${rule.rule_id}`, { enabled: !rule.enabled, change_note: note })
      toast(`${rule.rule_id} ${rule.enabled ? 'disabled' : 'enabled'}`, 'success')
      onSaved()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(false) }
  }
  return (
    <Modal title={`${rule.enabled ? 'Disable' : 'Enable'} ${rule.rule_id}`} onClose={onClose} footer={<>
      <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
      <Button busy={busy} disabled={note.trim().length < 3} onClick={save}>{rule.enabled ? 'Disable rule' : 'Enable rule'}</Button>
    </>}>
      <p className="muted">{rule.name}. This creates version {rule.version + 1}; the next pre-scrutiny run uses it.</p>
      <div className="field"><label>Reason (required)</label><input className="input" autoFocus value={note} onChange={e => setNote(e.target.value)} /></div>
    </Modal>
  )
}

function SettingsCard({ meta, onSaved }: { meta: Meta; onSaved: () => void }) {
  const { can, toast } = useSession()
  const [refDate, setRefDate] = useState(meta.settings.reference_date || '')
  const [maxMb, setMaxMb] = useState(meta.settings.max_upload_mb)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [srcBusy, setSrcBusy] = useState<string | null>(null)
  const editable = can('settings:edit')

  async function save() {
    setBusy(true)
    try {
      await api.put('/settings', { reference_date: refDate, max_upload_mb: maxMb, change_note: note || 'Settings updated' })
      toast('Settings saved', 'success')
      setNote('')
      onSaved()
    } catch (e) { toast((e as Error).message, 'error') } finally { setBusy(false) }
  }
  async function setMode(key: string, mode: string) {
    setSrcBusy(key)
    try {
      await api.put(`/sources/${key}`, { mode, change_note: 'Changed from settings page' })
      toast('Verification source updated', 'success')
      onSaved()
    } catch (e) { toast((e as Error).message, 'error') } finally { setSrcBusy(null) }
  }

  return (
    <div className="grid2" style={{ alignItems: 'start' }}>
      <div className="card">
        <div className="card-title">Global settings</div>
        <div className="stack">
          <div className="field"><label>Evaluation (reference) date for expiry checks</label>
            <input className="input" type="date" value={refDate} disabled={!editable} onChange={e => setRefDate(e.target.value)} />
            <span className="help">Empty = today. Currently evaluating as of {fmtDate(meta.effective_reference_date)}.</span></div>
          <div className="field"><label>Maximum upload size (MB)</label>
            <input className="input" type="number" min={1} max={100} value={maxMb} disabled={!editable} onChange={e => setMaxMb(Number(e.target.value))} /></div>
          {editable && <>
            <div className="field"><label>Reason for change</label><input className="input" value={note} onChange={e => setNote(e.target.value)} /></div>
            <Button busy={busy} onClick={save} style={{ alignSelf: 'flex-start' }}>Save settings</Button>
          </>}
        </div>
      </div>
      <div className="card">
        <div className="card-title">Verification sources</div>
        <div className="stack" style={{ gap: 14 }}>
          {meta.sources.map(s => (
            <div key={s.key}>
              <div className="row" style={{ alignItems: 'flex-start' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 500 }}>{s.name}</div>
                  <div className="faint" style={{ fontSize: 12 }}>{s.method} · {s.doc_types.join(', ')}</div>
                </div>
                <span className="spacer" />
                {s.is_mock && <MockTag />}
              </div>
              <select className="select" style={{ marginTop: 6 }} value={s.mode} disabled={!editable || srcBusy === s.key}
                      onChange={e => setMode(s.key, e.target.value)} aria-label={`Mode for ${s.name}`}>
                <option value="ONLINE">Online — answers immediately</option>
                <option value="ASYNC">Asynchronous — answer arrives later</option>
                <option value="OFFLINE">Unavailable — route to manual confirmation</option>
              </select>
            </div>
          ))}
          <p className="help">Prototype sources are simulated. Real integrations would use authorised issuing-authority APIs only.</p>
        </div>
      </div>
    </div>
  )
}

export default function RulesPage() {
  const { meta, can, refreshMeta } = useSession()
  const { data, error, loading, reload } = useApi(() => api.get<Rule[]>('/rules'), [])
  const [editing, setEditing] = useState<Rule | null | 'new'>(null)
  const [toggling, setToggling] = useState<Rule | null>(null)
  const [group, setGroup] = useState('ALL')
  const editable = can('rules:edit')

  if (!meta) return <div className="page"><Loading /></div>
  const rules = (data || []).filter(r => group === 'ALL' || r.group === group)
  const catLabel = (c: string) => meta.settings.categories.find(x => x.code === c)?.label || c

  return (
    <div className="page fade-up">
      <div className="row" style={{ alignItems: 'flex-end' }}>
        <div>
          <div className="eyebrow">Configuration</div>
          <h1 className="title">Regulatory rules &amp; checklists</h1>
          <p className="muted" style={{ marginTop: 4, maxWidth: 720 }}>
            Requirements are configuration, not code. Authorised administrators can enable or disable rules, change
            thresholds and severity, choose which application categories they apply to, and add new required documents.
            Every change creates a new rule version, and each validation result records the version it used.
          </p>
        </div>
        <span className="spacer" />
        {editable ? <button className="btn btn-primary" onClick={() => setEditing('new')}>New rule</button>
          : <span className="help">Read-only — editing requires the Administrator role</span>}
      </div>

      <div className="section"><SettingsCard meta={meta} onSaved={refreshMeta} /></div>

      <div className="section">
        <div className="chip-row" style={{ marginBottom: 14 }}>
          {['ALL', ...GROUPS].map(g => (
            <button key={g} className={`chip ${group === g ? 'active' : ''}`} onClick={() => setGroup(g)}>
              {g === 'ALL' ? 'All rules' : humanize(g)} ({(data || []).filter(r => g === 'ALL' || r.group === g).length})
            </button>
          ))}
        </div>
        {error ? <ErrorBox error={error} onRetry={reload} /> : loading && !data ? <Loading /> : (
          <div className="stack" style={{ gap: 10 }}>
            {rules.map(r => (
              <div key={r.rule_id} className={`rule-card ${r.enabled ? '' : 'disabled'}`}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600 }}>{r.name}</div>
                  <div className="muted" style={{ fontSize: 13, marginTop: 2 }}>{r.description}</div>
                  <div className="faint" style={{ fontSize: 12, marginTop: 6 }}>
                    <span className="mono">{r.rule_id}</span> · v{r.version} · {r.check_label}
                    {Object.keys(r.params || {}).length > 0 && <> · {Object.entries(r.params).map(([k, v]) => `${k}=${Array.isArray(v) ? (v as string[]).join('/') || '—' : v}`).join(', ')}</>}
                  </div>
                  {r.source_reference && <div className="faint" style={{ fontSize: 12 }}>Source: {r.source_reference}</div>}
                </div>
                <div>
                  <div className="kv-label">Applies to</div>
                  <div style={{ fontSize: 13 }}>{r.applies_to.map(catLabel).join(', ')}</div>
                </div>
                <div><div className="kv-label">Severity</div><Badge value={r.severity} label={humanize(r.severity)} /></div>
                <button className="btn btn-secondary btn-sm" onClick={() => setEditing(r)}>{editable ? 'Edit' : 'View'}</button>
                <button className={`toggle ${r.enabled ? 'on' : 'off'}`} disabled={!editable} aria-pressed={r.enabled}
                        aria-label={`${r.enabled ? 'Disable' : 'Enable'} ${r.rule_id}`} onClick={() => setToggling(r)}>
                  <div className="toggle-knob" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {editing && <RuleModal rule={editing === 'new' ? null : editing} meta={meta} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); reload(true) }} />}
      {toggling && <ToggleModal rule={toggling} onClose={() => setToggling(null)} onSaved={() => { setToggling(null); reload(true) }} />}
    </div>
  )
}
