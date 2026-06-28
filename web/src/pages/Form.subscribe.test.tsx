import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Form from './Form'

vi.mock('../auth/session', () => ({
  isAuthed: () => true, getIdToken: () => 'tok',
  authedFetch: vi.fn(async () => ({ ok: true, json: async () => ({ status: 'subscribed', delivery: 'active' }) })),
}))
vi.mock('../auth/login', () => ({ startLogin: vi.fn() }))

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (u: string) => {
    if (String(u).endsWith('/catalog')) return { ok: true, json: async () => ({
      categories: [{ name: '전체', sources: [{ key: 'aitimes', name: 'AI Times', lang: 'ko' }] }],
      lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5 }) }
    return { ok: true, json: async () => ({ subscribed: false, recipient: 'me@x.com', profile: {} }) }
  }) as unknown as typeof fetch)
})

describe('구독하기', () => {
  it('subscribes and shows delivery status', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('AI Times'))
    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.click(screen.getByRole('button', { name: /구독하기/ }))
    await waitFor(() => expect(screen.getByText(/구독 완료|매일/)).toBeInTheDocument())
  })
})
