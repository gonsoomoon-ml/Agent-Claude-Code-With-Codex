import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import Admin from './Admin'
import { isAdmin, isAuthed, authedFetch } from '../auth/session'
import { startLogin } from '../auth/login'

vi.mock('../auth/session', () => ({
  isAdmin: vi.fn(() => true),
  isAuthed: vi.fn(() => true),
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    emails: [{ user_id: 'u1', recipient: 'a@x.com', run_date: '2026-07-08',
      sent_at: '2026-07-08T07:00:12Z', published: 5, quarantined: 0,
      duration_ms: 662000, cost_usd: 1.08, status: 'sent', message_id: 'MID-1' }],
    totals: { count: 1, cost_usd: 1.08, avg_duration_ms: 662000 } }) })),
}))
vi.mock('../auth/login', () => ({ startLogin: vi.fn() }))

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })

describe('Admin dashboard', () => {
  it('발송 이메일 행과 비용을 렌더한다', async () => {
    vi.mocked(isAuthed).mockReturnValue(true)
    vi.mocked(isAdmin).mockReturnValue(true)
    render(<Admin />)
    expect(await screen.findByText('a@x.com')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText(/1\.08/)).toBeInTheDocument()
  })

  it('합계 줄(건수·비용·평균 소요)을 렌더한다', async () => {
    vi.mocked(isAuthed).mockReturnValue(true)
    vi.mocked(isAdmin).mockReturnValue(true)
    render(<Admin />)
    const totals = await screen.findByText(/합계/)
    expect(totals).toHaveTextContent('1건')
    expect(totals).toHaveTextContent('$1.08')
    expect(totals).toHaveTextContent('11m2s')
  })

  it('로그인은 됐지만 비admin 이면 관리자 전용 + fetch·재로그인 안 함', async () => {
    vi.mocked(isAuthed).mockReturnValue(true)
    vi.mocked(isAdmin).mockReturnValue(false)
    render(<Admin />)
    expect(await screen.findByText('관리자 전용')).toBeInTheDocument()
    expect(authedFetch).not.toHaveBeenCalled()
    expect(startLogin).not.toHaveBeenCalled()
  })

  it('일부 필드 누락 행이어도 크래시 없이 렌더한다(방어)', async () => {
    vi.mocked(isAuthed).mockReturnValue(true)
    vi.mocked(isAdmin).mockReturnValue(true)
    vi.mocked(authedFetch).mockResolvedValueOnce({ ok: true, json: async () => ({
      emails: [{ user_id: 'u2', recipient: 'b@x.com', run_date: '2026-07-09',
        sent_at: '2026-07-09T07:00Z', status: 'sent' }],   // published/duration_ms/cost_usd 누락
      totals: { count: 1 } }) } as unknown as Response)
    render(<Admin />)
    expect(await screen.findByText('b@x.com')).toBeInTheDocument()   // toFixed 크래시 없이 렌더
  })

  it('미로그인 시 로그인을 시작하고 복귀 경로(/admin)를 저장한다', async () => {
    vi.mocked(isAuthed).mockReturnValue(false)
    render(<Admin />)
    expect(startLogin).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('post_login')).toBe('/admin')
    expect(authedFetch).not.toHaveBeenCalled()
  })
})
