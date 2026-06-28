// 로그아웃: 토큰을 지우고 Cognito 호스팅 UI로 리다이렉트

import { AUTH } from './config'
import { clearTokens } from './session'

export function logout() {
  clearTokens()
  location.assign(`${AUTH.hostedUI}/logout?client_id=${AUTH.clientId}&logout_uri=${encodeURIComponent(AUTH.redirectUri())}`)
}
