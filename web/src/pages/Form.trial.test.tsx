import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Form from './Form'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).endsWith('/catalog')) return {
      ok: true, json: async () => ({
        categories: [{ name: '전체', sources: [{ key: 'aitimes', name: 'AI Times', lang: 'ko' }] }],
        lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5 }) }
    return { ok: true, status: 202, json: async () => ({ status: 'verification_pending' }) }
  }) as unknown as typeof fetch)
})

describe('체험하기', () => {
  it('enables 체험하기 after email + source, posts trial, shows pending', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('AI Times'))
    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'u@x.com' } })
    const btn = screen.getByRole('button', { name: /체험하기/ })
    expect(btn).not.toBeDisabled()
    fireEvent.click(btn)
    await waitFor(() => expect(screen.getByText(/확인 메일/)).toBeInTheDocument())
  })
})
