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
  // ★ ?code 정리는 여기서 raw history.replaceState 로 하지 않는다 — 그것은 react-router 의
  //   history state({usr,key,idx})를 지워(desync) 직후 navigate 를 깨뜨린다. URL 정리는
  //   CallbackRedirect 의 navigate 가 담당(react-router 가 history 를 올바로 관리).
}
