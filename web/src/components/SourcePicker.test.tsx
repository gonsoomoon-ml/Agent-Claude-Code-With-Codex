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
    // 선택 1 / 5 (최대 5개) — counter text is split across elements
    const counterElements = screen.getAllByText((content, element) => {
      return element?.textContent?.includes('선택') && element?.textContent?.includes('1') && element?.textContent?.includes('5') || false
    })
    expect(counterElements.length > 0).toBe(true)
    fireEvent.click(screen.getByLabelText('B'))
    expect(onChange).toHaveBeenCalledWith(['a', 'b'])
  })

  it('disables unchecked boxes at the limit', () => {
    render(<SourcePicker categories={cats} max={2} selected={['a', 'b']} onChange={() => {}} />)
    expect(screen.getByLabelText('C')).toBeDisabled()             // 상한 도달 → 미선택 비활성
    expect(screen.getByLabelText('A')).not.toBeDisabled()         // 선택된 건 해제 가능
  })
})
