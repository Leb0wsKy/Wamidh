import { describe, expect, it } from 'vitest'
import type { NavRoute } from '../api/types'
import { headingAt, pointAlong, prepare, progress, simulatedPosition } from './guidance'

// 891 m east along 36.80 N, then 1112 m north: one left turn, then a short walk east.
const route: NavRoute = {
  incident_id: 1,
  origin: { lon: 8.6, lat: 36.8, source: 'station' },
  target: { lon: 8.611, lat: 36.81, node_id: 5 },
  drive: {
    geometry: [
      [8.6, 36.8],
      [8.605, 36.8],
      [8.61, 36.8],
      [8.61, 36.81],
    ],
    distance_m: 2003,
    duration_s: 300,
    steps: [
      { kind: 'depart', road: { ref: 'RN17' }, distance_m: 891, location: [8.6, 36.8] },
      { kind: 'left', road: { fclass: 'track' }, distance_m: 1112, location: [8.61, 36.8] },
      { kind: 'arrive', road: { fclass: 'track' }, distance_m: 0, location: [8.61, 36.81] },
    ],
  },
  walk: {
    geometry: [
      [8.61, 36.81],
      [8.611, 36.81],
    ],
    distance_m: 89,
  },
}
const nav = prepare(route)

describe('progress along the route', () => {
  it('at the start: next manoeuvre is the left turn 891 m ahead', () => {
    const p = progress(nav, { lon: 8.6, lat: 36.8 })

    expect(p.phase).toBe('drive')
    expect(p.next?.kind).toBe('left')
    expect(p.toNextM).toBeCloseTo(891, -1)
    expect(p.remainingM).toBeCloseTo(2003 + 89, -1)
    expect(p.remainingS).toBeGreaterThan(300)
  })

  it('projects a slightly off-road fix onto the road', () => {
    const p = progress(nav, { lon: 8.605, lat: 36.8002 }) // ~22 m north of the road, halfway

    expect(p.offRouteM).toBeCloseTo(22, 0)
    expect(p.alongM).toBeCloseTo(446, -1)
    expect(p.toNextM).toBeCloseTo(446, -1)
  })

  it('after the turn the next instruction is the arrival at the access point', () => {
    const p = progress(nav, { lon: 8.61, lat: 36.805 })

    expect(p.next?.kind).toBe('arrive')
    expect(p.toNextM).toBeCloseTo(556, -1)
  })

  it('switches to walking at the access point, then arrives at the node', () => {
    expect(progress(nav, { lon: 8.61, lat: 36.81 }).phase).toBe('walk')
    expect(progress(nav, { lon: 8.61, lat: 36.81 }).toNextM).toBeCloseTo(89, -1)
    expect(progress(nav, { lon: 8.6109, lat: 36.81 }).phase).toBe('arrived')
  })

  it('reports how far a fix is from the road, to trigger a new route', () => {
    expect(progress(nav, { lon: 8.605, lat: 36.803 }).offRouteM).toBeGreaterThan(300)
  })

  it('does not jump back to an earlier part of the road that passes close by', () => {
    // A road that comes back 20 m from where it started (a hairpin).
    const hairpin = prepare({
      ...route,
      drive: {
        ...route.drive,
        geometry: [
          [8.6, 36.8],
          [8.61, 36.8],
          [8.61, 36.8002],
          [8.6, 36.8002],
        ],
        steps: [
          { kind: 'depart', road: {}, distance_m: 0, location: [8.6, 36.8] },
          { kind: 'arrive', road: {}, distance_m: 0, location: [8.6, 36.8002] },
        ],
      },
    })
    // Slightly closer to the outbound leg, but the truck is known to be on the way back.
    const late = progress(hairpin, { lon: 8.6001, lat: 36.80009 }, 1700)

    expect(late.alongM).toBeGreaterThan(1700)
  })
})

describe('pointAlong', () => {
  it('interpolates a position along the drive geometry', () => {
    const p = pointAlong(nav, 891 + 556)

    expect(p.lon).toBeCloseTo(8.61, 5)
    expect(p.lat).toBeCloseTo(36.805, 3)
    expect(pointAlong(nav, 99_999)).toEqual({ lon: 8.61, lat: 36.81 })
  })
})

describe('simulatedPosition', () => {
  it('drives at the route average speed, then walks to the node', () => {
    // 2003 m in 300 s: halfway after 150 s.
    expect(progress(nav, simulatedPosition(nav, 150)).alongM).toBeCloseTo(1001, -1)
    // Then 89 m on foot at 1.1 m/s (~81 s).
    const walking = simulatedPosition(nav, 300 + 40)
    expect(walking.lat).toBeCloseTo(36.81, 6)
    expect(walking.lon).toBeGreaterThan(8.61)
    expect(simulatedPosition(nav, 10_000)).toEqual({ lon: 8.611, lat: 36.81 })
  })
})

describe('a route requested from off the road', () => {
  it('counts the way from the vehicle to the road as part of the route', () => {
    // After a wrong turn the vehicle is 110 m south of the road it is routed back to.
    const fromForest = prepare({ ...route, origin: { lon: 8.6, lat: 36.799, source: 'gps' } })

    const p = progress(fromForest, { lon: 8.6, lat: 36.799 })

    expect(p.offRouteM).toBeLessThan(1)
    expect(p.remainingM).toBeCloseTo(111 + 2003 + 89, -1)
  })
})

describe('headingAt', () => {
  it('follows the road ahead, in degrees clockwise from north', () => {
    expect(headingAt(nav, 100)).toBeCloseTo(90, 0) // driving east
    expect(headingAt(nav, 1500)).toBeCloseTo(0, 0) // after the left turn, north
  })
})
