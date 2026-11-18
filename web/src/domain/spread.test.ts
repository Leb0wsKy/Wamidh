import { describe, expect, it } from 'vitest'
import { compassPoint, confidenceLevel, etaLabel, HORIZONS, toFireMinutes } from './spread'

describe('compassPoint', () => {
  it('names the eight directions, wrapping around north', () => {
    expect(compassPoint(0)).toBe('N')
    expect(compassPoint(92)).toBe('E')
    expect(compassPoint(225)).toBe('SW')
    expect(compassPoint(350)).toBe('N')
    expect(compassPoint(-90)).toBe('W')
  })
})

describe('confidenceLevel', () => {
  it('reads the share of plausible scenarios', () => {
    expect(confidenceLevel(0.8)).toBe('high')
    expect(confidenceLevel(0.3)).toBe('medium')
    expect(confidenceLevel(0.05)).toBe('low')
  })
})

describe('time', () => {
  it('offers now and four horizons', () => {
    expect(HORIZONS).toEqual([0, 15, 30, 60, 120])
  })

  it('converts fire minutes to clock seconds in an accelerated demo', () => {
    expect(toFireMinutes(30, 60)).toBe(30) // 30 s of clock = 30 fire minutes at x60
    expect(toFireMinutes(120, 1)).toBe(2)
  })

  it('formats an expected arrival', () => {
    expect(etaLabel(null)).toBe('—')
    expect(etaLabel(0.4)).toBe('< 1 min')
    expect(etaLabel(42.6)).toBe('~43 min')
    expect(etaLabel(135)).toBe('~2 h 15')
  })
})
