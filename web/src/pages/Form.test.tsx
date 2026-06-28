// web/src/pages/Form.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Form from './Form'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({
      categories: [{ name: '전체', sources: [{ key: 'a', name: 'A', lang: 'en' }] }],
      lenses: [], depths: [], send_hours: [6, 7, 8], max_sources: 5,
    }),
  })) as unknown as typeof fetch)
})

describe('Form', () => {
  it('renders catalog sources and send-hour options after load', async () => {
    render(<Form />)
    await waitFor(() => expect(screen.getByLabelText('A')).toBeInTheDocument())
    expect(screen.getByLabelText(/06:00/)).toBeInTheDocument()
    expect(screen.getByLabelText(/07:00/)).toBeInTheDocument()
    expect(screen.getByLabelText(/08:00/)).toBeInTheDocument()
  })

  it('keeps 체험하기 disabled in v1.0', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('A'))
    expect(screen.getByRole('button', { name: /체험하기/ })).toBeDisabled()
  })

  it('selects a source via checkbox', async () => {
    render(<Form />)
    await waitFor(() => screen.getByLabelText('A'))
    fireEvent.click(screen.getByLabelText('A'))
    expect(screen.getByLabelText('A')).toBeChecked()
  })
})
