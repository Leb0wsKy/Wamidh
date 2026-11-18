import { describe, expect, it } from 'vitest'
import { readingTone } from './readings'

describe('readingTone', () => {
  it('stays quiet for normal readings', () => {
    expect(readingTone('temp', 32)).toBe('normal')
    expect(readingTone('rh', 45)).toBe('normal')
    expect(readingTone('gas', 1.0)).toBe('normal')
    expect(readingTone('ai', 0.05)).toBe('normal')
    expect(readingTone('flame', false)).toBe('normal')
  })

  it('turns amber, then ember, as a reading points to fire', () => {
    expect(readingTone('temp', 41)).toBe('alert')
    expect(readingTone('temp', 58)).toBe('fire')
    expect(readingTone('rh', 15)).toBe('alert') // very dry air
    expect(readingTone('gas', 0.77)).toBe('alert') // smoke lowers the gas ratio
    expect(readingTone('gas', 0.4)).toBe('fire')
    expect(readingTone('ai', 0.42)).toBe('alert')
    expect(readingTone('ai', 0.9)).toBe('fire')
    expect(readingTone('flame', true)).toBe('fire')
  })

  it('is quiet when there is no value yet', () => {
    expect(readingTone('temp', null)).toBe('normal')
  })
})
