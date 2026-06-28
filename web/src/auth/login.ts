// 로그인 시작: Cognito 호스팅 UI로 리다이렉트

import { AUTH } from './config'
import { generateVerifier, generateChallenge, generateState } from './pkce'

export async function startLogin() {
  const verifier = generateVerifier(), state = generateState()
  sessionStorage.setItem('pkce_verifier', verifier)
  sessionStorage.setItem('pkce_state', state)
  const challenge = await generateChallenge(verifier)
  const q = new URLSearchParams({
    client_id: AUTH.clientId, response_type: 'code', scope: AUTH.scope,
    redirect_uri: AUTH.redirectUri(), state, code_challenge: challenge, code_challenge_method: 'S256',
  })
  location.assign(`${AUTH.hostedUI}/oauth2/authorize?${q}`)
}
