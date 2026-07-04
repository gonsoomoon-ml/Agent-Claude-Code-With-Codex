// Form.manage.test.tsx — 웹 프로필 관리 완성: lens·depth 라디오 노출 + 구독자 prefill
// (design/../docs/superpowers/specs/2026-07-04-web-profile-manage-design.md 테스트 계약)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Form from './Form'
import { authedFetch } from '../auth/session'

vi.mock('../auth/session', () => ({
  isAuthed: () => true,
  getIdToken: () => 'tok',
  authedFetch: vi.fn(),
}))
vi.mock('../auth/login', () => ({ startLogin: vi.fn() }))

const mockedAuthedFetch = vi.mocked(authedFetch)

const CATALOG = {
  categories: [{ name: '전체', sources: [
    { key: 'aitimes', name: 'AI Times', lang: 'ko' },
    { key: 'other', name: 'Other', lang: 'ko' },
  ] }],
  lenses: [{ key: 'general', name: '일반' }, { key: 'engineer', name: '엔지니어' }],
  depths: ['summary', 'full'],
  send_hours: [6, 7, 8],
  max_sources: 5,
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (u: string) => {
    if (String(u).endsWith('/catalog')) return { ok: true, json: async () => CATALOG }
    return { ok: true, json: async () => ({}) }
  }) as unknown as typeof fetch)
})

afterEach(() => vi.restoreAllMocks())

describe('프로필 관리 — 구독자 prefill', () => {
  it('subscribed profile 의 sources/send_hour/lens/depth 를 폼 상태에 반영한다', async () => {
    mockedAuthedFetch.mockImplementation(async () => ({
      ok: true,
      json: async () => ({
        subscribed: true,
        recipient: 'me@x.com',
        profile: { sources: ['aitimes', 'other'], send_hour: 6, lens: 'engineer', depth: 'full' },
        max_sources: 5,
      }),
    }) as unknown as Response)

    render(<Form />)

    await waitFor(() => expect(screen.getByLabelText('AI Times')).toBeChecked())
    expect(screen.getByLabelText('Other')).toBeChecked()
    expect(screen.getByLabelText('06:00 KST')).toBeChecked()
    expect(screen.getByLabelText('엔지니어')).toBeChecked()
    expect(screen.getByLabelText('full')).toBeChecked()
  })
})

describe('프로필 관리 — payload 하드코딩 제거', () => {
  it('lens/depth 라디오 변경 후 구독하기 → putProfile payload 에 선택한 값이 실린다', async () => {
    mockedAuthedFetch.mockImplementation(async (_path: string, init?: RequestInit) => {
      if (init?.method === 'PUT') {
        return {
          ok: true,
          json: async () => ({ status: 'subscribed', delivery: 'active' }),
        } as unknown as Response
      }
      return {
        ok: true,
        json: async () => ({ subscribed: false, recipient: 'me@x.com', profile: {} }),
      } as unknown as Response
    })

    render(<Form />)
    await waitFor(() => screen.getByLabelText('AI Times'))

    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.click(screen.getByLabelText('엔지니어'))
    fireEvent.click(screen.getByLabelText('full'))
    fireEvent.click(screen.getByRole('button', { name: /구독하기/ }))

    await waitFor(() => {
      const putCall = mockedAuthedFetch.mock.calls.find(([, init]) => init?.method === 'PUT')
      expect(putCall).toBeDefined()
    })

    const putCall = mockedAuthedFetch.mock.calls.find(([, init]) => init?.method === 'PUT')!
    const body = JSON.parse((putCall[1] as RequestInit).body as string)
    expect(body.lens).toBe('engineer')
    expect(body.depth).toBe('full')
  })
})
