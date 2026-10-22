import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { Button, ErrorBox, Logo } from '../components/ui'
import { useSession } from '../context'

interface DemoAccount { email: string; name: string; role: string; password: string }
const ROLE_LABEL: Record<string, string> = {
  SCRUTINY_OFFICER: 'Scrutiny Officer', VERIFICATION_OFFICER: 'Verification Officer', ADMIN: 'Administrator',
}
const ROLE_HINT: Record<string, string> = {
  SCRUTINY_OFFICER: 'Uploads, runs pre-scrutiny, acts on findings, records outcome',
  VERIFICATION_OFFICER: 'Runs and records issuing-authority verification',
  ADMIN: 'Configures rules, thresholds and verification sources',
}

function Instrument() {
  const labels = ['Application', 'Documents', 'Rules', 'Records', 'Verification']
  return (
    <svg width="260" height="260" viewBox="0 0 320 320" aria-hidden="true">
      <circle cx="160" cy="160" r="140" fill="none" stroke="#D8D0C3" />
      <circle cx="160" cy="160" r="120" fill="none" stroke="#D8D0C3" strokeWidth="0.5" strokeDasharray="4 6" />
      <circle cx="160" cy="160" r="100" fill="none" stroke="#D8D0C3" strokeWidth="0.5" />
      <circle cx="160" cy="160" r="40" fill="none" stroke="#9B3F2D" strokeWidth="1.5" opacity="0.6" />
      <circle cx="160" cy="160" r="4" fill="#9B3F2D" opacity="0.8" />
      <g style={{ animation: 'spinSlow 30s linear infinite', transformOrigin: '160px 160px' }}>
        <line x1="160" y1="160" x2="160" y2="24" stroke="#9B3F2D" opacity="0.3" />
        <circle cx="160" cy="48" r="3" fill="#9B3F2D" opacity="0.5" />
      </g>
      {labels.map((l, i) => {
        const a = (i / labels.length) * Math.PI * 2 - Math.PI / 2
        const x = 160 + Math.cos(a) * 130, y = 160 + Math.sin(a) * 130
        return (
          <g key={l}>
            <circle cx={x} cy={y} r="2.5" fill="#9B3F2D" opacity="0.4" />
            <text x={x} y={y - 10} textAnchor="middle" fontSize="9" fill="#918A80" fontWeight="500" letterSpacing="0.05em">{l.toUpperCase()}</text>
          </g>
        )
      })}
    </svg>
  )
}

export default function LoginPage() {
  const { login } = useSession()
  const [email, setEmail] = useState('scrutiny@verifyai.demo')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [accounts, setAccounts] = useState<DemoAccount[]>([])

  useEffect(() => { api.get<DemoAccount[]>('/auth/demo-accounts').then(setAccounts).catch(() => setAccounts([])) }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try { await login(email, password) } catch (err) { setError((err as Error).message) } finally { setBusy(false) }
  }

  return (
    <div className="login-wrap">
      <section className="login-hero fade-up">
        <div className="row" style={{ marginBottom: 40 }}>
          <Logo />
          <span style={{ fontWeight: 600 }}>AICTE <span style={{ color: 'var(--accent)' }}>VerifyAI</span></span>
        </div>
        <div className="eyebrow">AICTE Application Intelligence · SIH26261</div>
        <h1>Every application deserves a clearer <span className="accent">verification</span> path.</h1>
        <p className="muted" style={{ fontSize: 16, marginTop: 20, maxWidth: 480 }}>
          Evidence-first AI pre-scrutiny for application validation, document authentication and regulatory
          compliance. AI finds and organises the evidence. The authorised officer makes the decision.
        </p>
        <div style={{ marginTop: 32 }}><Instrument /></div>
      </section>
      <section className="login-panel">
        <form className="card" style={{ width: '100%', maxWidth: 420, padding: 28 }} onSubmit={submit}>
          <h2 className="title" style={{ fontSize: 26 }}>Sign in</h2>
          <p className="muted" style={{ marginTop: 4, marginBottom: 20 }}>Role-based access for authorised officials.</p>
          <div className="stack">
            <div className="field">
              <label htmlFor="email">Email</label>
              <input id="email" className="input" type="email" autoComplete="username" value={email}
                     onChange={e => setEmail(e.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="password">Password</label>
              <input id="password" className="input" type="password" autoComplete="current-password" value={password}
                     onChange={e => setPassword(e.target.value)} required />
            </div>
            {error && <ErrorBox error={error} />}
            <Button type="submit" busy={busy} style={{ padding: '11px 16px' }}>Enter review workspace</Button>
          </div>
          {accounts.length > 0 && (
            <div style={{ marginTop: 24 }}>
              <div className="card-title" style={{ marginBottom: 8 }}>Demo accounts (password {accounts[0].password})</div>
              <div className="stack" style={{ gap: 8 }}>
                {accounts.map(a => (
                  <button type="button" key={a.email} className="demo-account"
                          onClick={() => { setEmail(a.email); setPassword(a.password) }}>
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{ROLE_LABEL[a.role]} · {a.name}</div>
                      <div className="faint" style={{ fontSize: 12 }}>{ROLE_HINT[a.role]}</div>
                    </div>
                    <span className="faint" style={{ fontSize: 12 }}>Use →</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </form>
      </section>
    </div>
  )
}
