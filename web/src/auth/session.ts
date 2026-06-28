// 세션 관리 (in-memory id_token, XSS 방지를 위해 localStorage 사용 금지)

import { API_BASE } from '../api'

let _idToken: string | null = null

export function storeTokens(idToken: string) { _idToken = idToken }

export function getIdToken(): string | null { return _idToken }

export function clearTokens() { _idToken = null }

export function isAuthed(): boolean { return _idToken != null }

export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = { ...(init.headers || {}), Authorization: `Bearer ${_idToken ?? ''}` }
  return fetch(path.startsWith('http') ? path : `${API_BASE}${path}`, { ...init, headers })
}
