import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Form from './Form'

vi.mock('../auth/session', () => ({
  isAuthed: () => true, getIdToken: () => 'tok',
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    subscribed: false, recipient: 'admin@x.com', profile: {}, max_sources: 6 }) })),
}))
vi.mock('../auth/login', () => ({ startLogin: vi.fn() }))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (u: string) => {
    if (String(u).endsWith('/catalog')) return { ok: true, json: async () => ({
      categories: [{ name: '전체', sources: [
        { key: 'a', name: 'A', lang: 'ko' }, { key: 'b', name: 'B', lang: 'ko' },
        { key: 'c', name: 'C', lang: 'ko' }, { key: 'd', name: 'D', lang: 'ko' },
        { key: 'e', name: 'E', lang: 'ko' }, { key: 'f', name: 'F', lang: 'ko' } ] }],
      lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5 }) }
    return { ok: true, json: async () => ({}) }
  }) as unknown as typeof fetch)
})

describe('admin max_sources', () => {
  it('프로필의 max_sources(6)가 헤딩과 카운터에 반영된다', async () => {
    render(<Form />)
    // "(최대 6개)" 텍스트는 h2 헤딩과 SourcePicker 카운터(선택 0 / 6 (최대 6개)) 두 곳에 렌더되어
    // findByText(단일 매치 기대)가 충돌 → findAllByText 로 두 곳 모두 6 을 반영했는지 확인
    const maxTexts = await screen.findAllByText(/최대 6개/)
    expect(maxTexts.length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/선택\s*0\s*\/\s*6/)).toBeInTheDocument()
  })
})
