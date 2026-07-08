import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import Admin from './Admin'
import { isAdmin, authedFetch } from '../auth/session'

vi.mock('../auth/session', () => ({
  isAdmin: vi.fn(() => true),
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    emails: [{ user_id: 'u1', recipient: 'a@x.com', run_date: '2026-07-08',
      sent_at: '2026-07-08T07:00:12Z', published: 5, quarantined: 0,
      duration_ms: 662000, cost_usd: 1.08, status: 'sent', message_id: 'MID-1' }],
    totals: { count: 1, cost_usd: 1.08, avg_duration_ms: 662000 } }) })),
}))

beforeEach(() => vi.clearAllMocks())

describe('Admin dashboard', () => {
  it('발송 이메일 행과 비용을 렌더한다', async () => {
    vi.mocked(isAdmin).mockReturnValue(true)
    render(<Admin />)
    expect(await screen.findByText('a@x.com')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText(/1\.08/)).toBeInTheDocument()
  })

  it('합계 줄(건수·비용·평균 소요)을 렌더한다', async () => {
    vi.mocked(isAdmin).mockReturnValue(true)
    render(<Admin />)
    const totals = await screen.findByText(/합계/)
    expect(totals).toHaveTextContent('1건')
    expect(totals).toHaveTextContent('$1.08')
    expect(totals).toHaveTextContent('11m2s')
  })

  it('비admin 은 관리자 전용 메시지를 보이고 authedFetch 를 호출하지 않는다', async () => {
    vi.mocked(isAdmin).mockReturnValue(false)
    render(<Admin />)
    expect(await screen.findByText('관리자 전용')).toBeInTheDocument()
    expect(authedFetch).not.toHaveBeenCalled()
  })
})
