import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import CallbackRedirect from './CallbackRedirect'
import { handleCallback } from './callback'

const navigate = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }))
vi.mock('./callback', () => ({ handleCallback: vi.fn(async () => {}) }))

beforeEach(() => { vi.clearAllMocks(); sessionStorage.clear() })

describe('CallbackRedirect', () => {
  it('콜백 후 post_login 경로로 client-side 이동하고 값을 지운다', async () => {
    sessionStorage.setItem('post_login', '/admin')
    render(<CallbackRedirect />)
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/admin', { replace: true }))
    expect(sessionStorage.getItem('post_login')).toBeNull()
  })

  it('post_login 이 없으면 이동하지 않는다', async () => {
    render(<CallbackRedirect />)
    await waitFor(() => expect(handleCallback).toHaveBeenCalled())
    expect(navigate).not.toHaveBeenCalled()
  })
})
