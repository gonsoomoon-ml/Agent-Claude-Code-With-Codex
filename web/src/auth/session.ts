// 세션 관리 (in-memory id_token, XSS 방지를 위해 localStorage 사용 금지)

import { API_BASE } from '../api'

let _idToken: string | null = null

export function storeTokens(idToken: string) { _idToken = idToken }

export function getIdToken(): string | null { return _idToken }

export function clearTokens() { _idToken = null }

export function isAuthed(): boolean { return _idToken != null }

/** id_token payload 의 cognito:groups 에 'admins' 포함 여부 — 백엔드 _parse_groups 와 동형(배열·문자열 모두 수용). */
export function isAdmin(): boolean {
  const tok = getIdToken()
  if (!tok) return false
  try {
    const payload = JSON.parse(atob(tok.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    const g = payload['cognito:groups']
    const groups = Array.isArray(g) ? g : String(g ?? '').replace(/[[\]]/g, '').split(/[ ,]+/)
    return groups.includes('admins')
  } catch {
    return false
  }
}

export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = { ...(init.headers || {}), Authorization: `Bearer ${_idToken ?? ''}` }
  return fetch(path.startsWith('http') ? path : `${API_BASE}${path}`, { ...init, headers })
}
