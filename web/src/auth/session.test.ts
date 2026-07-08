import { describe, it, expect, beforeEach } from 'vitest'
import { isAdmin, storeTokens, clearTokens } from './session'

const fakeJwt = (payload: unknown) => `h.${btoa(JSON.stringify(payload))}.s`

beforeEach(() => clearTokens())

describe('isAdmin', () => {
  it('토큰이 없으면 false', () => {
    expect(isAdmin()).toBe(false)
  })

  it('JWT 형식이 아닌/깨진 문자열이면 예외 없이 false', () => {
    storeTokens('not-a-jwt')
    expect(isAdmin()).toBe(false)
  })

  it('cognito:groups 가 배열 ["admins"] 이면 true', () => {
    storeTokens(fakeJwt({ 'cognito:groups': ['admins'] }))
    expect(isAdmin()).toBe(true)
  })

  it('cognito:groups 가 평탄화된 문자열 "[admins]" 이면 true', () => {
    storeTokens(fakeJwt({ 'cognito:groups': '[admins]' }))
    expect(isAdmin()).toBe(true)
  })

  it('cognito:groups 가 ["user"] 뿐이면 false', () => {
    storeTokens(fakeJwt({ 'cognito:groups': ['user'] }))
    expect(isAdmin()).toBe(false)
  })
})
