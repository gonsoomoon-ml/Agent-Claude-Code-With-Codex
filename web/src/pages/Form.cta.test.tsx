// Form.cta.test.tsx — v1.1f: 체험하기 primary 코랄 pill(순서·클래스·게이트 보존)
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import Form from './Form'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).endsWith('/catalog')) return {
      ok: true, json: async () => ({
        categories: [{ name: '전체', sources: [{ key: 'aitimes', name: 'AI Times', lang: 'ko' }] }],
        lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5,
      }),
    }
    return { ok: true, status: 202, json: async () => ({ status: 'verification_pending' }) }
  }) as unknown as typeof fetch)
})
afterEach(() => vi.restoreAllMocks())

describe('v1.1f CTA 코랄 pill', () => {
  it('체험하기 = primary coral pill (first, cta-coral); sibling = ghost; disabled gate preserved', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('AI Times'))

    // 액션행 버튼은 정확히 2개(<button>); 소스=checkbox·시각=radio 는 제외
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveClass('cta-coral')        // 체험하기 primary, 첫 자식
    expect(buttons[0].textContent).toMatch(/체험하기/)
    expect(buttons[1]).toHaveClass('cta-ghost')        // 로그인/구독하기 강등
    expect(buttons[1].textContent).toMatch(/구독하기/)

    // disabled 게이트 보존: 출처/이메일 전엔 disabled
    expect(buttons[0]).toBeDisabled()
    fireEvent.click(screen.getByLabelText('AI Times'))
    fireEvent.change(screen.getByPlaceholderText('you@example.com'), { target: { value: 'u@x.com' } })
    expect(screen.getByRole('button', { name: /체험하기/ })).not.toBeDisabled()
  })
})
