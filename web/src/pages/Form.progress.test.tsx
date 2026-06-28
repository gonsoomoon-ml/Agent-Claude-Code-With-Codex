// Form.progress.test.tsx — 체험하기 폴링 진행 UI TDD
// fake timers (setInterval/clearInterval 만) 로 3s 간격 폴링 제어
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import Form from './Form'

const CATALOG = {
  categories: [{ name: '전체', sources: [{ key: 'aitimes', name: 'AI Times', lang: 'ko' }] }],
  lenses: [],
  depths: [],
  send_hours: [6, 7, 8],
  max_sources: 5,
}

describe('Form 진행 UI (폴링)', () => {
  beforeEach(() => {
    // setInterval/clearInterval 만 fake — setTimeout 은 실제 유지(waitFor 호환)
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('체험하기 클릭 → 버튼 loading → 카드 "생성 중" → 카드 "발송 완료"', async () => {
    let statusCallCount = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, _init?: RequestInit) => {
        const u = String(url)
        if (u.endsWith('/catalog')) {
          return { ok: true, json: async () => CATALOG }
        }
        if (u.includes('/trial/status')) {
          statusCallCount++
          // 1차 폴링: generating, 2차+: sent
          if (statusCallCount === 1) {
            return { ok: true, json: async () => ({ status: 'generating' }) }
          }
          return { ok: true, json: async () => ({ status: 'sent', published: 8 }) }
        }
        // POST /trial → 202 accepted (비동기 생성 시작)
        return { ok: true, status: 202, json: async () => ({ status: 'generating' }) }
      }) as unknown as typeof fetch,
    )

    render(<Form />)
    // 카탈로그 로드 대기 (setTimeout 은 실제라 waitFor 동작)
    await waitFor(() => screen.getByLabelText('AI Times'))

    // 소스 선택 + 이메일 입력
    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), {
      target: { value: 'u@x.com' },
    })

    const btn = screen.getByRole('button', { name: /체험하기/ })
    expect(btn).not.toBeDisabled()

    // 체험하기 클릭 → postTrial awaited → polling 시작
    await act(async () => {
      fireEvent.click(btn)
    })

    // 버튼이 "보내는 중…" disabled 로 전환
    expect(screen.getByRole('button', { name: /보내는 중/ })).toBeDisabled()
    // StatusCard 카드 표시
    expect(screen.getByRole('status')).toBeInTheDocument()

    // 3s 진행 → 첫 번째 폴링 → 'generating'
    await act(async () => {
      vi.advanceTimersByTime(3000)
      // 비동기 fetch mock 마이크로태스크 플러시
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText(/생성 중/)).toBeInTheDocument()

    // 다시 3s → 두 번째 폴링 → 'sent'
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(screen.getByText(/발송 완료/)).toBeInTheDocument()
  })
})
