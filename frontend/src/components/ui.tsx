import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

type Tone = 'critical' | 'warning' | 'success' | 'info' | 'muted'

const TONES: Record<string, Tone> = {
  // severities
  CRITICAL: 'critical', WARNING: 'warning', INFO: 'info',
  // application statuses
  DRAFT: 'muted', SUBMITTED: 'info', PROCESSING: 'info', NEEDS_REVIEW: 'warning',
  CLARIFICATION_REQUESTED: 'warning', READY_FOR_DECISION: 'success', DECIDED: 'success',
  // verification statuses
  VERIFIED: 'success', MISMATCH: 'critical', EXPIRED: 'warning', PENDING: 'info',
  SOURCE_UNAVAILABLE: 'info', MANUAL_REVIEW: 'warning', NOT_REQUESTED: 'muted',
  // finding statuses
  OPEN: 'critical', ESCALATED: 'critical', REVIEWED: 'success', AUTO_CLEARED: 'muted',
  // rule outcomes
  PASS: 'success', FAIL: 'critical', WARN: 'warning', DISABLED: 'muted', ERROR: 'critical',
  // document statuses
  UPLOADED: 'info', PROCESSED: 'success', FAILED: 'critical', SUPERSEDED: 'muted', REMOVED: 'muted',
}

const LABELS: Record<string, string> = {
  CRITICAL: 'Critical', WARNING: 'Warning', INFO: 'Pending',
  DRAFT: 'Draft', SUBMITTED: 'Awaiting pre-scrutiny', PROCESSING: 'Pre-scrutiny running', NEEDS_REVIEW: 'Needs review',
  CLARIFICATION_REQUESTED: 'Clarification requested', READY_FOR_DECISION: 'Ready for decision', DECIDED: 'Outcome recorded',
  VERIFIED: 'Verified', MISMATCH: 'Mismatch detected', EXPIRED: 'Expired', PENDING: 'Verification pending',
  SOURCE_UNAVAILABLE: 'Source unavailable', MANUAL_REVIEW: 'Manual review required', NOT_REQUESTED: 'Not requested',
  OPEN: 'Open', ESCALATED: 'Escalated', REVIEWED: 'Reviewed', AUTO_CLEARED: 'Cleared on re-run',
  PASS: 'Passed', FAIL: 'Failed', WARN: 'Warning', DISABLED: 'Disabled', ERROR: 'Error',
  UPLOADED: 'Not processed', PROCESSED: 'Processed', FAILED: 'Failed', SUPERSEDED: 'Superseded', REMOVED: 'Removed',
}

export function toneOf(value: string): Tone { return TONES[value] || 'muted' }

export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={`badge tone-${toneOf(value)}`}>
      <span className="badge-dot" />{label || LABELS[value] || value}
    </span>
  )
}

export function MockTag() {
  return <span className="mock-tag" title="Simulated source for the prototype — not a real external integration">MOCK SOURCE</span>
}

export function Loading({ text = 'Loading…' }: { text?: string }) {
  return <div className="loading"><span className="spinner" /> {text}</div>
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="error-box row">
      <span>{error}</span>
      <span className="spacer" />
      {onRetry && <button className="btn btn-secondary btn-sm" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Modal({ title, onClose, children, footer, wide }: {
  title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  // Portal to <body>: animated (transformed) ancestors would otherwise trap position: fixed
  return createPortal(
    <div className="overlay" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="close-x" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>,
    document.body,
  )
}

export function Button({ busy, children, className = 'btn-primary', ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button className={`btn ${className}`} disabled={busy || rest.disabled} {...rest}>
      {busy && <span className="spinner" />}{children}
    </button>
  )
}

export function DocIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" style={{ flexShrink: 0 }}>
      <rect x="2" y="1" width="10" height="12" rx="1.5" stroke="#6E685F" strokeWidth="1" />
      <line x1="4" y1="5" x2="10" y2="5" stroke="#D8D0C3" strokeWidth="0.8" />
      <line x1="4" y1="7.5" x2="8" y2="7.5" stroke="#D8D0C3" strokeWidth="0.8" />
    </svg>
  )
}

export function Logo() {
  return (
    <div className="logo-icon">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M7 1L12 4V10L7 13L2 10V4L7 1Z" stroke="white" strokeWidth="1.5" fill="none" />
        <circle cx="7" cy="7" r="2" fill="white" />
      </svg>
    </div>
  )
}

export function Disclaimer() {
  return (
    <div className="disclaimer">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="none" stroke="#918A80" /><path d="M8 4.5v4.5M8 11v.5" stroke="#918A80" strokeWidth="1.5" strokeLinecap="round" /></svg>
      <span>AI-assisted findings are <b>advisory indicators</b> backed by evidence. Statutory scrutiny, inspection and the final decision remain with the authorised AICTE officer.</span>
    </div>
  )
}

export function NeedsRole({ role }: { role: string }) {
  return <span className="help">Requires the {role} role</span>
}
