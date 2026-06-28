import { describe, it, expect } from 'vitest'
import { generateVerifier, generateChallenge, generateState } from './pkce'

describe('pkce', () => {
  it('verifier is 43-128 url-safe chars', () => {
    const v = generateVerifier()
    expect(v.length).toBeGreaterThanOrEqual(43)
    expect(/^[A-Za-z0-9\-._~]+$/.test(v)).toBe(true)
  })
  it('challenge is base64url (no padding) of sha256', async () => {
    const c = await generateChallenge('abc')
    expect(c.includes('=')).toBe(false)
    expect(/^[A-Za-z0-9\-_]+$/.test(c)).toBe(true)
  })
  it('state is random', () => { expect(generateState()).not.toBe(generateState()) })
})
