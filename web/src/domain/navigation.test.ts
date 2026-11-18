import { describe, expect, it } from 'vitest'
import { bearingLabel, distanceKm } from './navigation'

describe('distanceKm', () => {
  it('is zero for the same point and ~111 km per degree of latitude', () => {
    expect(distanceKm({ lat: 36.8, lon: 8.7 }, { lat: 36.8, lon: 8.7 })).toBe(0)
    expect(distanceKm({ lat: 36, lon: 8.7 }, { lat: 37, lon: 8.7 })).toBeCloseTo(111.2, 0)
  })
})

describe('bearingLabel', () => {
  it('names the compass direction from the nodes to the station', () => {
    expect(bearingLabel({ lat: 36.75, lon: 8.61 }, { lat: 36.95, lon: 8.79 })).toBe('NE')
    expect(bearingLabel({ lat: 36.75, lon: 8.61 }, { lat: 36.5, lon: 8.61 })).toBe('S')
  })
})
