// Form.trial.test.tsx — 체험하기 UI: StatusCard 로 확인 메일 안내 표시
// NOTE: <p>{msg}</p> → <StatusCard> 로 교체됨에 따라 role="status" 를 단언
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import Form from './Form'

beforeEach(() => {
  // setInterval/clearInterval 만 fake — setTimeout 은 실제 유지(waitFor 호환)
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  vi.stubGlobal('fetch', vi.fn(async (url: string, _init?: RequestInit) => {
    if (String(url).endsWith('/catalog')) return {
      ok: true, json: async () => ({
        categories: [{ name: '전체', sources: [{ key: 'aitimes', name: 'AI Times', lang: 'ko' }] }],
        lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5,
      }),
    }
    if (String(url).includes('/trial/status')) return {
      ok: true, json: async () => ({ status: 'sent', published: 1 }),
    }
    // POST /trial → 202, body.status = 'verification_pending'
    return { ok: true, status: 202, json: async () => ({ status: 'verification_pending' }) }
  }) as unknown as typeof fetch)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('체험하기', () => {
  it('enables 체험하기 after email + source, posts trial, shows verification_pending in StatusCard', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('AI Times'))
    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'u@x.com' } })
    const btn = screen.getByRole('button', { name: /체험하기/ })
    expect(btn).not.toBeDisabled()

    // 클릭 → postTrial awaited
    await act(async () => { fireEvent.click(btn) })

    // StatusCard 가 표시되고 확인 메일 안내 텍스트 포함
    await waitFor(() => expect(screen.getByRole('status')).toBeInTheDocument())
    expect(screen.getByText(/확인 메일/)).toBeInTheDocument()

    // 3s 진행 → 첫 번째 폴링(sent) → 인터벌 정리
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
  })
})
