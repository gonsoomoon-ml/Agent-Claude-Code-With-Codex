import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SourcePicker } from './SourcePicker'
import type { Category } from '../types'

const cats: Category[] = [
  { name: '전체', sources: [
    { key: 'a', name: 'A', lang: 'en' }, { key: 'b', name: 'B', lang: 'ko' },
    { key: 'c', name: 'C', lang: 'en' },
  ] },
]

describe('SourcePicker', () => {
  it('shows remaining counter and toggles selection', () => {
    const onChange = vi.fn()
    render(<SourcePicker categories={cats} max={5} selected={['a']} onChange={onChange} />)
    // 선택 1 / 5 (최대 5개) — strong assertion on counter format
    expect(screen.getByText(/선택\s*1\s*\/\s*5/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('B'))
    expect(onChange).toHaveBeenCalledWith(['a', 'b'])
  })

  it('disables unchecked boxes at the limit', () => {
    render(<SourcePicker categories={cats} max={2} selected={['a', 'b']} onChange={() => {}} />)
    expect(screen.getByLabelText('C')).toBeDisabled()             // 상한 도달 → 미선택 비활성
    expect(screen.getByLabelText('A')).not.toBeDisabled()         // 선택된 건 해제 가능
  })

  it('renders each source as a card (label.src-card) reflecting selection', () => {
    render(<SourcePicker categories={cats} max={5} selected={['a']} onChange={() => {}} />)
    const aCard = screen.getByLabelText('A').closest('label')
    expect(aCard).toHaveClass('src-card')                 // 카드 구조
    expect(screen.getByLabelText('A')).toBeChecked()      // 선택 반영
    expect(screen.getByLabelText('B')).not.toBeChecked()
    expect(document.querySelector('.src-grid')).toBeTruthy()  // 그리드 컨테이너
  })
})
