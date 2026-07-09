import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import CallbackRedirect from './CallbackRedirect'
import { handleCallback } from './callback'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('./callback', () => ({ handleCallback: vi.fn(async () => {}) }))

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  history.replaceState({}, '', '/')   // URL 초기화(테스트 간 ?code 누수 방지)
})

describe('CallbackRedirect', () => {
  it('콜백(?code)이면 post_login 경로로 이동하고 값을 지운다', async () => {
    history.replaceState({}, '', '/?code=C&state=S')
    sessionStorage.setItem('post_login', '/admin')
    render(<CallbackRedirect />)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/admin', { replace: true }))
    expect(sessionStorage.getItem('post_login')).toBeNull()
  })

  it('콜백(?code)이지만 post_login 이 없으면 현재 경로로 정리 이동(?code 제거)', async () => {
    history.replaceState({}, '', '/?code=C&state=S')
    render(<CallbackRedirect />)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }))
  })

  // ★ 레이스 회귀: 콜백이 아닌 일반 로드(?code 없음)에서는 post_login 을 건드리면 안 된다.
  //   (그렇지 않으면 /admin 로드 시 Admin 이 심은 post_login 을 리다이렉트 전에 지워버린다.)
  it('콜백이 아니면(?code 없음) handleCallback·navigate 를 호출하지 않고 post_login 을 보존한다', async () => {
    sessionStorage.setItem('post_login', '/admin')
    render(<CallbackRedirect />)
    await new Promise((r) => setTimeout(r))   // effect + microtask 소진
    expect(handleCallback).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
    expect(sessionStorage.getItem('post_login')).toBe('/admin')
  })
})
