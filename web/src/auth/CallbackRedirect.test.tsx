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
  it('post_login 이 있으면 그 경로로 client-side 이동하고 값을 지운다', async () => {
    sessionStorage.setItem('post_login', '/admin')
    render(<CallbackRedirect />)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/admin', { replace: true }))
    expect(sessionStorage.getItem('post_login')).toBeNull()
  })

  it('post_login 없고 ?code 도 없으면 이동하지 않는다', async () => {
    render(<CallbackRedirect />)
    await waitFor(() => expect(handleCallback).toHaveBeenCalled())
    expect(navigate).not.toHaveBeenCalled()
  })

  it('post_login 없지만 ?code 가 있으면 현재 경로로 정리 이동(?code 제거)', async () => {
    history.replaceState({}, '', '/?code=abc&state=xyz')
    render(<CallbackRedirect />)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }))
  })
})
