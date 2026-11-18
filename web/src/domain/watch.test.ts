import { describe, expect, it } from 'vitest'
import type { Incident, SensorNode } from '../api/types'
import { activity24h, recentEvents, watchItems } from './watch'
import { fire } from '../test/fixtures'

const NOW = Date.parse('2026-10-05T12:00:00Z')
const node = (id: number, extra: Partial<SensorNode> = {}): SensorNode => ({
  id,
  state: 'NORMAL',
  lon: 8.6,
  lat: 36.7,
  last_seen: '2026-10-05T11:59:50Z',
  battery_v: 3.9,
  risk_percentile: 99,
  gateway_id: 31,
  link: { received: 100, lost: 0, rejected: 0 },
  ...extra,
})

describe('watchItems', () => {
  it('is empty when every sensor is healthy', () => {
    expect(watchItems([node(1), node(2)])).toEqual([])
  })

  it('lists silent sensors first, then low batteries and lossy radio links', () => {
    const items = watchItems([
      node(1, { battery_v: 3.42 }),
      node(2, { state: 'OFFLINE', last_seen: '2026-10-05T11:00:00Z' }),
      node(3, { link: { received: 90, lost: 10, rejected: 0 } }),
      node(4, { state: 'LOST_PROBABLY_BURNED' }),
      node(5),
    ])

    expect(items.map((i) => [i.nodeId, i.kind])).toEqual([
      [4, 'lost'],
      [2, 'silent'],
      [1, 'battery'],
      [3, 'radio'],
    ])
    expect(items.find((i) => i.kind === 'battery')).toMatchObject({ value: 3.42 })
    expect(items.find((i) => i.kind === 'radio')).toMatchObject({ value: 10 })
  })

  it('ignores a sensor that has not reported yet for battery and radio', () => {
    expect(watchItems([node(1, { battery_v: null, link: undefined })])).toEqual([])
  })
})

describe('activity24h', () => {
  const inc = (id: number, status: string, created: string, node = 3) =>
    ({ id, status, created_at: created, first_node_id: node }) as unknown as Incident

  it('counts fires, false alarms and sensors alarmed in the last 24 h, with the latest fire', () => {
    const a = activity24h(
      [
        inc(9, 'CLOSED', '2026-10-05T10:00:00Z', 2),
        inc(8, 'FALSE_ALARM', '2026-10-05T08:00:00Z'),
        inc(7, 'EN_ROUTE', '2026-10-05T11:30:00Z', 4),
        inc(6, 'CLOSED', '2026-10-03T10:00:00Z'), // older than 24 h
      ],
      [
        node(1, { last_alert_at: '2026-10-05T09:00:00Z' }),
        node(2, { last_alert_at: '2026-10-01T09:00:00Z' }), // too old
        node(3),
      ],
      NOW,
    )

    expect(a).toEqual({
      fires: 2,
      falseAlarms: 1,
      alertedSensors: 1,
      lastFire: { nodeId: 4, at: '2026-10-05T11:30:00Z' },
    })
  })

  it('has no last fire when there was none', () => {
    expect(activity24h([], [], NOW).lastFire).toBeNull()
  })
})

describe('recentEvents', () => {
  const withEvents = (id: number, events: [string, string][]) => ({
    ...fire(id, id, 'ACKNOWLEDGED'),
    events: events.map(([ts, type]) => ({ ts, type, payload: {} })),
  })

  it('merges every incident log, newest first, and keeps the latest few', () => {
    const incidents = [
      withEvents(1, [
        ['2026-10-01T12:00:00Z', 'node_fire'],
        ['2026-10-01T12:05:00Z', 'acknowledged'],
      ]),
      withEvents(2, [['2026-10-01T12:03:00Z', 'node_fire']]),
    ]

    const recent = recentEvents(incidents, 2)

    expect(recent.map((r) => [r.incident.id, r.event.type])).toEqual([
      [1, 'acknowledged'],
      [2, 'node_fire'],
    ])
  })
})
