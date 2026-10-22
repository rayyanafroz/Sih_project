import { Link, NavLink, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Loading, Logo } from './components/ui'
import { useSession } from './context'
import ApplicationsPage from './pages/Applications'
import AuditLogPage from './pages/AuditLog'
import DashboardPage from './pages/Dashboard'
import LoginPage from './pages/Login'
import ReportPage from './pages/Report'
import RulesPage from './pages/Rules'
import WorkspacePage from './pages/Workspace'

function Nav() {
  const { user, logout, can } = useSession()
  const links = [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/applications', label: 'Applications' },
    { to: '/rules', label: can('rules:edit') ? 'Rules & Settings' : 'Rules' },
    ...(can('audit:view_all') ? [{ to: '/audit', label: 'Audit log' }] : []),
  ]
  return (
    <nav className="top-nav">
      <Link to="/dashboard" className="logo">
        <Logo />
        <span>AICTE <span style={{ color: 'var(--accent)' }}>VerifyAI</span></span>
      </Link>
      <div className="nav-links">
        {links.map(l => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>{l.label}</NavLink>
        ))}
      </div>
      <span className="spacer" />
      <span className="demo-chip" title="All institutions, documents and external sources in this prototype are synthetic">
        Synthetic demo data
      </span>
      <div className="nav-user">
        <span className="officer-dot" />
        <div style={{ lineHeight: 1.2 }}>
          <div style={{ fontWeight: 500 }}>{user?.name}</div>
          <div className="faint" style={{ fontSize: 11 }}>{user?.role_label}</div>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={logout}>Sign out</button>
      </div>
    </nav>
  )
}

export default function App() {
  const { user, ready, sessionExpired } = useSession()
  const location = useLocation()
  if (!ready) return <div className="page"><Loading /></div>
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* Only an expired session returns the next sign-in to the same page; explicit sign-out starts fresh. */}
        <Route path="*" element={<Navigate to="/login" replace state={sessionExpired ? { from: location.pathname } : null} />} />
      </Routes>
    )
  }
  const isReport = location.pathname.endsWith('/report')
  return (
    <>
      {!isReport && <Nav />}
      <Routes>
        <Route path="/login" element={<Navigate to={(location.state as { from?: string })?.from || '/dashboard'} replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/applications/:id/report" element={<ReportPage />} />
        <Route path="/applications/:id/:tab?" element={<WorkspacePage />} />
        <Route path="/rules" element={<RulesPage />} />
        <Route path="/audit" element={<AuditLogPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  )
}
