import { describe, expect, it } from 'vitest'
import type { AlertZoneProps, Incident, PublicAlert } from '../api/types'
import { fire } from '../test/fixtures'
import { alertsSent, broadcastBlock, toLatLngs, zoneAlert, zoneCentre, zoneLabel } from './zones'

const t = (key: string, opts?: Record<string, unknown>) =>
  `${key}${opts ? JSON.stringify(opts) : ''}`

const zone = (extra: Partial<AlertZoneProps>): AlertZoneProps => ({
  id: 4,
  name: null,
  near: null,
  population: 120,
  risk_level: 'high',
  risk_percentile: 91,
  building_count: 12,
  tower_ids: [],
  ...extra,
})

const alert = (id: number, zones: number[], active = true): PublicAlert => ({
  id,
  incident_id: 7,
  created_at: '2026-10-01T12:10:00Z',
  zones: zones.map((z) => ({ id: z, label: `z${z}` })),
  people: 100,
  headline: 'تحذير',
  message_ar: 'تحذير',
  status: 'Exercise',
  delivery: 'simulated',
  active,
})

describe('zoneLabel', () => {
  it('uses the place name, else "douar near", else a numbered zone', () => {
    expect(zoneLabel(zone({ name: 'عين دراهم' }), t)).toBe('عين دراهم')
    expect(zoneLabel(zone({ near: 'بلطة' }), t)).toBe('residents.douarNear{"place":"بلطة"}')
    expect(zoneLabel(zone({}), t)).toBe('residents.zoneN{"id":4}')
  })
})

describe('zoneAlert', () => {
  it('finds the newest active alert covering the zone', () => {
    const alerts = [alert(9, [4, 5]), alert(8, [4]), alert(7, [6])]

    expect(zoneAlert(4, alerts)?.id).toBe(9)
    expect(zoneAlert(1, alerts)).toBeUndefined()
    expect(zoneAlert(4, [alert(3, [4], false)])).toBeUndefined()
  })
})

describe('broadcast rules', () => {
  const withAlert = (i: Incident): Incident => ({
    ...i,
    events: [
      ...i.events,
      { ts: '2026-10-01T12:09:00Z', type: 'public_alert', payload: { people: 900 } },
    ],
  })

  it('needs an acknowledged, open incident and at least one zone', () => {
    expect(broadcastBlock(fire(7, 1, 'STATION_NOTIFIED'), 1)).toBe('ack')
    expect(broadcastBlock(fire(7, 1, 'CLOSED'), 1)).toBe('closed')
    expect(broadcastBlock(fire(7, 1, 'ACKNOWLEDGED'), 0)).toBe('noZone')
    expect(broadcastBlock(fire(7, 1, 'EN_ROUTE'), 2)).toBeNull()
  })

  it('lists the alerts already sent, from the audit log', () => {
    expect(alertsSent(fire(7, 1, 'ACKNOWLEDGED'))).toEqual([])
    expect(alertsSent(withAlert(fire(7, 1, 'ACKNOWLEDGED')))).toEqual([
      { ts: '2026-10-01T12:09:00Z', people: 900 },
    ])
  })
})

describe('map geometry', () => {
  const square = (lon: number, lat: number, d: number) => [
    [
      [lon - d, lat - d],
      [lon + d, lat - d],
      [lon + d, lat + d],
      [lon - d, lat + d],
      [lon - d, lat - d],
    ],
  ]

  it('turns a MultiPolygon into Leaflet lat,lon rings', () => {
    const rings = toLatLngs({ type: 'MultiPolygon', coordinates: [square(8.7, 36.8, 0.01)] })

    expect(rings).toHaveLength(1)
    const [lat, lon] = rings[0]?.[0]?.[0] ?? [0, 0]
    expect(lat).toBeCloseTo(36.79, 9)
    expect(lon).toBeCloseTo(8.69, 9)
  })

  it('puts the centre in the largest part of the zone', () => {
    const geometry = {
      type: 'MultiPolygon' as const,
      coordinates: [square(8.6, 36.7, 0.001), square(8.7, 36.8, 0.01)],
    }

    const [lat, lon] = zoneCentre(geometry)
    expect(lat).toBeCloseTo(36.8, 6)
    expect(lon).toBeCloseTo(8.7, 6)
  })
})
