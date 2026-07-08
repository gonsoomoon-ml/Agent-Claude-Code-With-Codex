import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import Admin from './Admin'

vi.mock('../auth/session', () => ({
  isAdmin: () => true,
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({
    emails: [{ user_id: 'u1', recipient: 'a@x.com', run_date: '2026-07-08',
      sent_at: '2026-07-08T07:00:12Z', published: 5, quarantined: 0,
      duration_ms: 662000, cost_usd: 1.08, status: 'sent', message_id: 'MID-1' }],
    totals: { count: 1, cost_usd: 1.08, avg_duration_ms: 662000 } }) })),
}))

beforeEach(() => vi.clearAllMocks())

describe('Admin dashboard', () => {
  it('발송 이메일 행과 비용을 렌더한다', async () => {
    render(<Admin />)
    expect(await screen.findByText('a@x.com')).toBeInTheDocument()
    expect(await screen.findByText(/1\.08/)).toBeInTheDocument()
  })
})
