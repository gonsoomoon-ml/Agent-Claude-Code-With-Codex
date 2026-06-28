// web/src/api.ts — API 호출. 빌드 시 VITE_API_BASE(절대 URL); dev 는 ''(Vite 프록시).
import { authedFetch } from './auth/session'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? ''

export async function fetchCatalog(): Promise<import('./types').Catalog> {
  const r = await fetch(`${API_BASE}/catalog`)
  if (!r.ok) throw new Error(`catalog ${r.status}`)
  return r.json()
}

export async function postTrial(payload: {
  email: string; sources: string[]; depth?: string; lens?: string; timezone?: string
}): Promise<{ status?: string; error?: string; httpStatus: number }> {
  const r = await fetch(`${API_BASE}/trial`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
  })
  const body = await r.json()
  return { ...body, httpStatus: r.status }
}

export async function getTrialStatus(email: string): Promise<{ status: string; published?: number }> {
  const r = await fetch(`${API_BASE}/trial/status?email=${encodeURIComponent(email)}`)
  return r.json()
}

export async function getProfile(): Promise<{ subscribed?: boolean; recipient?: string; delivery?: string; profile?: Record<string, unknown> }> {
  const r = await authedFetch('/profile')
  if (!r.ok) throw new Error(`profile ${r.status}`)
  return r.json()
}

export async function putProfile(payload: {
  sources?: string[]; send_hour?: number; lens?: string; depth?: string; timezone?: string; type?: string
}): Promise<{ status?: string; delivery?: string; error?: string }> {
  const r = await authedFetch('/profile', {
    method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload),
  })
  if (!r.ok) throw new Error(`profile ${r.status}`)
  return r.json()
}

export function sampleUrl(): string {
  return `${API_BASE}/sample`
}
