// 콜백 핸들러: 인증 코드를 받아 state 검증 후 token 교환

import { AUTH } from './config'
import { storeTokens } from './session'

export async function handleCallback(): Promise<void> {
  const p = new URLSearchParams(location.search)
  const code = p.get('code'); if (!code) return
  const state = p.get('state')
  const saved = sessionStorage.getItem('pkce_state')
  const verifier = sessionStorage.getItem('pkce_verifier')
  if (!state || state !== saved) throw new Error('state mismatch (CSRF)')
  if (!verifier) throw new Error('missing PKCE verifier')
  const body = new URLSearchParams({
    grant_type: 'authorization_code', client_id: AUTH.clientId, code,
    redirect_uri: AUTH.redirectUri(), code_verifier: verifier,
  })
  const r = await fetch(`${AUTH.hostedUI}/oauth2/token`, {
    method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body })
  if (!r.ok) throw new Error(`token ${r.status}`)
  const t = await r.json()
  storeTokens(t.id_token)
  sessionStorage.removeItem('pkce_state'); sessionStorage.removeItem('pkce_verifier')
  history.replaceState({}, '', location.pathname)   // ?code 제거
}
