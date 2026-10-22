// Typed client for the FastAPI backend (/api/v1).

export const API_BASE = '/api/v1'
const TOKEN_KEY = 'verifyai.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage unavailable: session-only login */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn }

function errorMessage(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const d = (body as { detail: unknown }).detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      return d.map((e: { loc?: unknown[]; msg?: string }) =>
        `${(e.loc || []).filter(x => x !== 'body').join('.')}: ${e.msg}`).join('; ')
    }
  }
  return fallback
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res: Response
  try {
    res = await fetch(API_BASE + path, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Cannot reach the VerifyAI server. Is the backend running?')
  }
  const text = await res.text()
  let data: unknown = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') onUnauthorized()
    throw new ApiError(res.status, errorMessage(data, `Request failed (${res.status})`))
  }
  return data as T
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

/** Upload with progress (fetch has no upload progress events). */
export function uploadWithProgress<T>(path: string, form: FormData, onProgress: (pct: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', API_BASE + path)
    const token = getToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)) }
    xhr.onload = () => {
      let data: unknown = null
      try { data = JSON.parse(xhr.responseText) } catch { data = xhr.responseText }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T)
      else {
        if (xhr.status === 401) onUnauthorized()
        reject(new ApiError(xhr.status, errorMessage(data, `Upload failed (${xhr.status})`)))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, 'Upload failed: cannot reach the server'))
    xhr.send(form)
  })
}

/** URL for <img>/<a> tags, which cannot send an Authorization header. */
export function fileUrl(path: string, params: Record<string, string> = {}): string {
  const q = new URLSearchParams({ ...params, token: getToken() || '' })
  return `${API_BASE}${path}?${q.toString()}`
}

// ── Types ──
export type Severity = 'CRITICAL' | 'WARNING' | 'INFO'

export interface User {
  id: number; name: string; email: string; role: string; role_label: string; permissions: string[]
}

export interface ParamSpec { name: string; type: string; label: string; default: unknown; help: string }

export interface Meta {
  document_types: { code: string; label: string; has_expiry: boolean; keywords: string[]; filename_hints: string[] }[]
  checks: { name: string; label: string; description: string; params: ParamSpec[] }[]
  settings: { reference_date: string; max_upload_mb: number; allowed_extensions: string[]; categories: { code: string; label: string }[] }
  effective_reference_date: string
  status_labels: Record<string, string>
  role_labels: Record<string, string>
  ocr_available: boolean
  sources: VerificationSource[]
}

export interface VerificationSource { id: number; key: string; name: string; doc_types: string[]; method: string; mode: string; is_mock: boolean }

export interface Run {
  id: number; application_id: number; mode: string; status: 'RUNNING' | 'COMPLETED' | 'FAILED'
  step_index: number; step_detail: string; steps: string[]; started_at: string; finished_at: string | null
  reference_date: string; summary: Record<string, number>; error: string | null
}

export interface ApplicationSummary {
  id: number; code: string; category: string; category_label: string; academic_year: string
  status: string; status_label: string; submitted_at: string
  institution: { id: number; name: string; aicte_id: string; state: string }
  open_findings: number; open_critical: number
  outcome: string | null; outcome_note: string | null; outcome_at: string | null; outcome_by: User | null
}

export interface ApplicationDetail extends ApplicationSummary {
  form_data: { institution_name: string; address: string; programmes: { programme: string; intake: number }[]; built_up_area_sqm: number | null }
  documents: { total: number; processed: number; failed: number }
  rules: { passed: number; evaluated: number }
  verification: { verified: number; total: number; pending: number }
  findings: { critical: number; warning: number; info: number; open: number; reviewed: number; cleared: number }
  last_run: Run | null; last_completed_run: Run | null; needs_rerun: boolean; demo_documents_available: boolean
}

export interface Verification {
  id: number; document_id: number; application_id: number; source_key: string | null; source_name: string
  is_mock: boolean; method: string; query: Record<string, string>; status: string
  response: Record<string, unknown>; comparison: { field: string; label: string; submitted: string; official: string; match: boolean }[]
  message: string; requested_by: string; requested_at: string; responded_at: string | null
}

export interface ExtractedField {
  id: number; field: string; value: string; normalized_value: string | null; page: number | null
  bbox: number[] | null; confidence: number; method: string
}

export interface DocumentInfo {
  id: number; application_id: number; filename: string; declared_type: string | null; detected_type: string | null
  effective_type: string; classification_confidence: number | null; mime: string; size: number; sha256: string
  page_count: number; text_method: string | null; ocr_confidence: number | null; status: string; error: string | null
  metadata: Record<string, string>; uploaded_at: string; processed_at: string | null
  replaces_document_id: number | null; field_count: number; verification: Verification | null
  fields?: ExtractedField[]
  pages?: { page_no: number; width: number; height: number; method: string; ocr_confidence: number | null; text: string }[]
  application_code?: string
}

export interface Evidence {
  kind: 'document' | 'record' | 'application_form' | 'verification' | 'checklist' | 'metadata'
  label: string; value?: string | null; document_id?: number; application_id?: number; filename?: string
  page?: number; bbox?: number[] | null; field?: string | null; source?: string; reference?: string | null
  is_mock?: boolean; method?: string; verification_id?: number
}

export interface Finding {
  id: number; application_id: number; finding_type: string; severity: Severity; status: string; title: string
  description: string; rule_id: string | null; rule_version: number | null; source_document_id: number | null
  source_page: number | null; source_field: string | null; evidence: Evidence[]; expected_value: string | null
  actual_value: string | null; confidence: number | null; recommended_action: string; created_at: string
  updated_at: string; resolved_at: string | null; resolution_note: string | null; run_id: number | null
  actions?: { id: number; action: string; note: string; actor: string; at: string }[]
}

export interface RuleResult {
  rule_id: string; rule_version: number; rule_name: string; group: string; severity: Severity; outcome: string
  message: string; finding_ids: number[]; evidence: Evidence[]; evaluated_at: string
}

export interface Rule {
  id: number; rule_id: string; name: string; description: string; group: string; check: string; check_label: string
  params: Record<string, unknown>; param_specs: ParamSpec[]; severity: Severity; applies_to: string[]; enabled: boolean
  version: number; source_reference: string; updated_at: string; updated_by: string
  history?: { version: number; snapshot: Record<string, unknown>; change_note: string; changed_by: string; changed_at: string }[]
}

export interface AuditEntry {
  id: number; at: string; actor_type: 'system' | 'user'; actor: string; actor_role: string | null; action: string
  entity_type: string | null; entity_id: string | null; application_id: number | null; summary: string
  details: Record<string, unknown>; application_code?: string | null
}

export interface Alert {
  severity: Severity; kind: string; message: string; application_id: number; application_code: string
  finding_id: number | null; at: string
}
