import { describe, it, expect, vi, beforeEach } from 'vitest'
import { handleCallback } from './callback'

beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

describe('handleCallback', () => {
  it('throws on state mismatch (CSRF)', async () => {
    sessionStorage.setItem('pkce_state', 'GOOD'); sessionStorage.setItem('pkce_verifier', 'V')
    history.replaceState({}, '', '/?code=C&state=EVIL')
    await expect(handleCallback()).rejects.toThrow(/state/i)
  })
  it('no-op when no code param', async () => {
    history.replaceState({}, '', '/')
    await expect(handleCallback()).resolves.toBeUndefined()
  })
})
