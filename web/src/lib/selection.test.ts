import { describe, it, expect } from 'vitest'
import { toggleSource } from './selection'

describe('toggleSource (MAX-5)', () => {
  it('adds a key under the limit', () => {
    expect(toggleSource(['a'], 'b', 5)).toEqual(['a', 'b'])
  })
  it('removes an already-selected key', () => {
    expect(toggleSource(['a', 'b'], 'a', 5)).toEqual(['b'])
  })
  it('ignores add when at the limit', () => {
    const five = ['a', 'b', 'c', 'd', 'e']
    expect(toggleSource(five, 'f', 5)).toEqual(five)         // 6번째 추가 거부
  })
  it('still allows removing when at the limit', () => {
    const five = ['a', 'b', 'c', 'd', 'e']
    expect(toggleSource(five, 'c', 5)).toEqual(['a', 'b', 'd', 'e'])
  })
})
