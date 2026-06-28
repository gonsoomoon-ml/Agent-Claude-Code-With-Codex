import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ProgressModal } from './ProgressModal'

describe('ProgressModal', () => {
  it('renders dialog with text + 닫기, busy shows timer/note', () => {
    render(<ProgressModal title="브리핑 체험" text="⏳ 생성 중…" busy elapsedSec={48} onClose={() => {}} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/생성 중/)).toBeInTheDocument()
    expect(screen.getByText(/0:48/)).toBeInTheDocument()
    expect(screen.getByText(/닫아도/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /닫기/ })).toBeInTheDocument()
  })
  it('닫기 click → onClose', () => {
    const onClose = vi.fn()
    render(<ProgressModal title="x" text="✅ 발송 완료!" busy={false} elapsedSec={0} onClose={onClose} />)
    fireEvent.click(screen.getByRole('button', { name: /닫기/ }))
    expect(onClose).toHaveBeenCalled()
  })
  it('Escape → onClose', () => {
    const onClose = vi.fn()
    render(<ProgressModal title="x" text="t" busy elapsedSec={0} onClose={onClose} />)
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})
