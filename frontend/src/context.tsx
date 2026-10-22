import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler, type Meta, type User } from './api'

interface Toast { id: number; kind: 'info' | 'success' | 'error'; text: string }

interface Session {
  user: User | null
  meta: Meta | null
  ready: boolean
  /** True when the server rejected the session (expiry), as opposed to an explicit sign-out. */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  can: (permission: string) => boolean
  refreshMeta: () => Promise<void>
  toast: (text: string, kind?: Toast['kind']) => void
  docTypeLabel: (code: string | null | undefined) => string
}

const Ctx = createContext<Session | null>(null)

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [ready, setReady] = useState(false)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((text: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random()
    setToasts(t => [...t, { id, kind, text }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === 'error' ? 6000 : 3500)
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setUser(null)
    setMeta(null)
    setSessionExpired(false)
  }, [])

  const refreshMeta = useCallback(async () => {
    setMeta(await api.get<Meta>('/meta'))
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => { logout(); setSessionExpired(true) })
    if (!getToken()) { setReady(true); return }
    Promise.all([api.get<User>('/auth/me'), api.get<Meta>('/meta')])
      .then(([u, m]) => { setUser(u); setMeta(m) })
      .catch(() => setToken(null))
      .finally(() => setReady(true))
  }, [logout])

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post<{ token: string; user: User }>('/auth/login', { email, password })
    setToken(res.token)
    setSessionExpired(false)
    setUser(res.user)
    setMeta(await api.get<Meta>('/meta'))
  }, [])

  const can = useCallback((p: string) => !!user?.permissions.includes(p), [user])
  const docTypeLabel = useCallback((code: string | null | undefined) => {
    if (!code) return '—'
    return meta?.document_types.find(t => t.code === code)?.label || code
  }, [meta])

  return (
    <Ctx.Provider value={{ user, meta, ready, sessionExpired, login, logout, can, refreshMeta, toast, docTypeLabel }}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map(t => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}
      </div>
    </Ctx.Provider>
  )
}

export function useSession(): Session {
  const s = useContext(Ctx)
  if (!s) throw new Error('useSession outside provider')
  return s
}
