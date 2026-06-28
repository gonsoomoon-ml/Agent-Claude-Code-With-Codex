import { describe, it, expect, vi, afterEach } from 'vitest'
import { fetchCatalog } from './api'

afterEach(() => vi.restoreAllMocks())

describe('fetchCatalog', () => {
  it('parses catalog JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ categories: [], lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5 }),
    })) as unknown as typeof fetch)
    const cat = await fetchCatalog()
    expect(cat.max_sources).toBe(5)
    expect(cat.send_hours).toEqual([6, 7, 8])
  })

  it('throws on non-ok', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })) as unknown as typeof fetch)
    await expect(fetchCatalog()).rejects.toThrow('catalog 500')
  })
})
