import { describe, expect, it } from 'vitest'
import type { Incident, SensorNode } from '../api/types'
import { situation } from './overview'

const node = (id: number, state: SensorNode['state'], extra: Partial<SensorNode> = {}) =>
  ({
    id,
    state,
    lon: 8.6,
    lat: 36.7,
    last_seen: '2026-10-01T12:00:00Z',
    battery_v: 4.0,
    risk_percentile: 99,
    gateway_id: 30 + id,
    link: { received: 100, lost: 0, rejected: 0 },
    ...extra,
  }) as SensorNode

describe('situation', () => {
  it('all quiet: every sensor online, no loss, battery range', () => {
    const s = situation(
      [node(1, 'NORMAL', { battery_v: 3.9 }), node(2, 'NORMAL', { battery_v: 4.1 })],
      [],
    )
    expect(s).toMatchObject({
      level: 'normal',
      online: 2,
      total: 2,
      alerts: 0,
      fires: 0,
      gateways: 2,
      lossPct: 0,
      batteryMin: 3.9,
    })
    expect(s.batteryAvg).toBeCloseTo(4.0)
  })

  it('counts silent sensors as offline and computes packet loss over all links', () => {
    const s = situation(
      [
        node(1, 'ALERT', { link: { received: 90, lost: 10, rejected: 0 } }),
        node(2, 'OFFLINE', { gateway_id: 31, link: { received: 100, lost: 0, rejected: 0 } }),
        node(3, 'NORMAL', { gateway_id: 31 }),
      ],
      [],
    )
    // Nodes 1 and 3 share gateway 31; node 2 is silent, so its gateway is not counted.
    expect(s).toMatchObject({ level: 'alert', online: 2, total: 3, alerts: 1, gateways: 1 })
    expect(s.lossPct).toBeCloseTo((10 / 300) * 100)
  })

  it('is a fire while a sensor reports fire or an incident still burns', () => {
    expect(situation([node(1, 'FIRE')], []).level).toBe('fire')
    expect(situation([node(1, 'FIRE')], []).fires).toBe(1)
    const burning = { status: 'EN_ROUTE' } as Incident
    expect(situation([node(1, 'NORMAL')], [burning]).level).toBe('fire')
    const settled = { status: 'UNDER_CONTROL' } as Incident
    expect(situation([node(1, 'NORMAL')], [settled]).level).toBe('normal')
  })

  it('reports the most recent contact, and copes with no data yet', () => {
    const s = situation(
      [node(1, 'NORMAL'), node(2, 'NORMAL', { last_seen: '2026-10-01T12:00:30Z' })],
      [],
    )
    expect(s.lastReport).toBe('2026-10-01T12:00:30Z')
    expect(situation([], [])).toMatchObject({ total: 0, batteryMin: null, lastReport: null })
  })
})
