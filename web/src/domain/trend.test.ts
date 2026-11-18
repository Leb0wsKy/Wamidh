import { describe, expect, it } from 'vitest'
import { sparkPath } from './trend'

describe('sparkPath', () => {
  it('scales values into the box, lowest at the bottom', () => {
    expect(sparkPath([10, 20, 30], 100, 20)).toBe('M0,20L50,10L100,0')
  })

  it('draws a flat line in the middle when nothing changes, nothing without data', () => {
    expect(sparkPath([5, 5], 10, 20)).toBe('M0,10L10,10')
    expect(sparkPath([], 10, 20)).toBe('')
  })
})
