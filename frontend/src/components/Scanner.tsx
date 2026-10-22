import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { api, type Run } from '../api'

/** Full-screen pre-scrutiny progress. Polls the real run; steps and counts come from the backend. */
export default function Scanner({ appId, appCode, initial, onDone }: {
  appId: number; appCode: string; initial: Run; onDone: () => void
}) {
  const [run, setRun] = useState<Run>(initial)
  const [pollError, setPollError] = useState<string | null>(null)

  useEffect(() => {
    if (run.status !== 'RUNNING') return
    const t = setTimeout(async () => {
      try {
        const runs = await api.get<Run[]>(`/applications/${appId}/runs`)
        const latest = runs.find(r => r.id === run.id) || runs[0]
        if (latest) setRun(latest)
        setPollError(null)
      } catch (e) { setPollError((e as Error).message) }
    }, 500)
    return () => clearTimeout(t)
  }, [run, appId])

  const complete = run.status === 'COMPLETED'
  const failed = run.status === 'FAILED'
  const steps = run.steps
  const idx = complete ? steps.length : run.step_index
  const pct = complete ? 100 : Math.round(((run.step_index + 0.5) / steps.length) * 100)
  const s = run.summary || {}

  const check = <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 6L5 8.5L9.5 3.5" stroke="#55705B" strokeWidth="1.5" fill="none" strokeLinecap="round" /></svg>

  return createPortal(
    <div className="scanner-overlay" role="dialog" aria-modal="true" aria-label="Pre-scrutiny progress">
      <div className="eyebrow">AI pre-scrutiny · {run.mode === 'FULL' ? 'full analysis' : 'rules only'}</div>
      <h2 className="title" style={{ marginBottom: 32, textAlign: 'center' }}>
        {complete ? 'Pre-scrutiny complete.' : failed ? 'Pre-scrutiny failed.' : `Analysing application ${appCode}`}
      </h2>
      <div className="scanner-box">
        {!complete && !failed && <div className="scan-line" style={{ top: `${pct}%` }} />}
        {steps.map((label, i) => {
          const done = i < idx
          const active = i === idx && !complete && !failed
          return (
            <div key={label} className="scan-step" style={{ opacity: i <= idx ? 1 : 0.3 }}>
              <div className={`scan-node ${done ? 'done' : active ? 'active' : ''}`}>
                {done ? check : active ? <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)' }} /> : null}
              </div>
              <div>
                <div style={{ fontWeight: 500, color: done ? 'var(--success)' : active ? 'var(--ink)' : 'var(--faint)' }}>{label}</div>
                {active && <div className="muted" style={{ fontSize: 13 }}>{run.step_detail}</div>}
              </div>
            </div>
          )
        })}
        <div className="progress" style={{ marginTop: 20 }}>
          <div style={{ width: `${pct}%`, background: complete ? 'var(--success)' : failed ? 'var(--accent)' : undefined }} />
        </div>
        {failed && <div className="error-box" style={{ marginTop: 16 }}>{run.error}</div>}
        {pollError && <div className="help" style={{ marginTop: 10 }}>Connection issue, retrying… ({pollError})</div>}
      </div>
      {complete && (
        <div className="scan-results">
          {[
            { n: s.rules_evaluated, l: 'rules evaluated', c: 'var(--ink)' },
            { n: s.rules_passed, l: 'passed', c: 'var(--success)' },
            { n: s.findings_critical, l: 'critical', c: 'var(--accent)' },
            { n: s.findings_warning, l: 'warnings', c: 'var(--warning)' },
            { n: s.findings_info, l: 'pending verification', c: 'var(--info)' },
          ].map(m => (
            <div key={m.l}>
              <div className="scan-result-num" style={{ color: m.c }}>{m.n ?? 0}</div>
              <div className="muted" style={{ fontSize: 12, textAlign: 'center' }}>{m.l}</div>
            </div>
          ))}
        </div>
      )}
      {(complete || failed) && (
        <button className="btn btn-primary" style={{ marginTop: 28 }} onClick={onDone} autoFocus>
          {complete ? 'Review evidence-linked findings' : 'Back to application'}
        </button>
      )}
    </div>,
    document.body,
  )
}
