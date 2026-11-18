import { describe, expect, it } from 'vitest'
import { batteryLevel, formatElapsed, shortAgo } from './status'

describe('formatElapsed', () => {
  it('counts minutes:seconds since detection, hours once past one hour', () => {
    expect(formatElapsed(0)).toBe('0:00')
    expect(formatElapsed(42_400)).toBe('0:42')
    expect(formatElapsed(9 * 60_000 + 5_000)).toBe('9:05')
    expect(formatElapsed(3_600_000 + 2 * 60_000 + 3_000)).toBe('1:02:03')
    expect(formatElapsed(-5_000)).toBe('0:00') // clock skew between phone and server
  })
})

describe('batteryLevel', () => {
  it('maps the cell voltage to a 0-1 charge level', () => {
    expect(batteryLevel(4.2)).toBe(1)
    expect(batteryLevel(3.3)).toBe(0)
    expect(batteryLevel(3.75)).toBeCloseTo(0.5)
    expect(batteryLevel(5)).toBe(1)
    expect(batteryLevel(null)).toBeNull()
  })
})

describe('shortAgo', () => {
  it('says seconds, minutes, hours, then days', () => {
    expect(shortAgo(3_400)).toBe('3 s')
    expect(shortAgo(119_000)).toBe('119 s')
    expect(shortAgo(5 * 60_000)).toBe('5 min')
    expect(shortAgo(3 * 3_600_000)).toBe('3 h')
    expect(shortAgo(50 * 3_600_000)).toBe('2 d')
  })

  it('uses the units of the interface language', () => {
    const ar = { s: 'ث', min: 'د', h: 'س', d: 'ي' }
    expect(shortAgo(9_000, ar)).toBe('9 ث')
    expect(shortAgo(3 * 3_600_000, ar)).toBe('3 س')
  })
})
