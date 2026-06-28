import { describe, it, expect } from 'vitest'
import { trialStatusMessage, isTerminal } from './trialStatus'

describe('trialStatus', () => {
  it('maps status to copy + done flag', () => {
    expect(trialStatusMessage('generating').done).toBe(false)
    expect(trialStatusMessage('sent', 8).text).toMatch(/8/)
    expect(trialStatusMessage('sent', 8).done).toBe(true)
    expect(trialStatusMessage('fallback').done).toBe(true)
    expect(trialStatusMessage('expired').done).toBe(true)
    expect(trialStatusMessage('verification_pending').done).toBe(false)
  })
  it('isTerminal', () => {
    expect(isTerminal('sent')).toBe(true)
    expect(isTerminal('generating')).toBe(false)
  })
})
