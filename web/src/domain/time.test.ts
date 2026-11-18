import { describe, expect, it } from 'vitest'
import { formatClock, formatCount, formatDateTime } from './time'

describe('formatDateTime', () => {
  it('shows day/month and hour:minute in Tunisian time', () => {
    expect(formatDateTime('2026-10-05T12:02:00Z')).toBe('05/10 13:02')
    expect(formatDateTime('2026-10-05T23:30:00Z')).toBe('06/10 00:30')
  })
})

describe('formatClock', () => {
  it('gives hours and minutes in Tunisian time', () => {
    expect(formatClock('2026-10-01T12:09:40Z')).toBe('13:09')
  })
})

describe('formatCount', () => {
  it('groups thousands the way each language does, with Western digits', () => {
    expect(formatCount(21620, 'en')).toBe('21,620')
    expect(formatCount(21620, 'ar')).toBe('21.620')
  })
})
