// Population alert zones and public alerts (ADR 0003): naming, and when a broadcast is allowed.

import type { AlertZone, AlertZoneProps, Incident, PublicAlert } from '../api/types'
import { awaitingStation, isOpen } from './incident'

type T = (key: string, opts?: Record<string, unknown>) => string

/** The zone's place name; a douar is named after the nearest place. */
export function zoneLabel(zone: AlertZoneProps, t: T): string {
  if (zone.name) return zone.name
  if (zone.near) return t('residents.douarNear', { place: zone.near })
  return t('residents.zoneN', { id: zone.id })
}

/** The newest alert still active that reached this zone (alerts come newest first). */
export function zoneAlert(zoneId: number, alerts: PublicAlert[]): PublicAlert | undefined {
  return alerts.find((a) => a.active && a.zones.some((z) => z.id === zoneId))
}

export type BroadcastBlock = 'ack' | 'closed' | 'noZone'

/** Why the alert cannot be broadcast yet, or null when it can (the backend checks it too). */
export function broadcastBlock(incident: Incident, zoneCount: number): BroadcastBlock | null {
  if (!isOpen(incident.status)) return 'closed'
  if (awaitingStation(incident)) return 'ack'
  if (zoneCount === 0) return 'noZone'
  return null
}

/** Public alerts already broadcast for this incident, oldest first, from its audit log. */
export function alertsSent(incident: Incident): { ts: string; people: number }[] {
  return incident.events
    .filter((e) => e.type === 'public_alert')
    .map((e) => ({ ts: e.ts, people: Number(e.payload.people) }))
}

type MultiPolygon = AlertZone['geometry']
type LatLng = [number, number]

/** Leaflet wants [lat, lon]; GeoJSON gives [lon, lat]. One entry per part, rings inside. */
export function toLatLngs(geometry: MultiPolygon): LatLng[][][] {
  return geometry.coordinates.map((rings) =>
    rings.map((ring) => ring.map(([lon, lat]) => [lat, lon] as LatLng)),
  )
}

/** Signed area and centroid of a ring (shoelace), in degrees: fine at a village's scale. */
function ringCentroid(ring: number[][]): { area: number; lon: number; lat: number } {
  let a = 0
  let cx = 0
  let cy = 0
  let prev: number[] | undefined
  for (const point of ring) {
    if (prev) {
      const [x0 = 0, y0 = 0] = prev
      const [x1 = 0, y1 = 0] = point
      const cross = x0 * y1 - x1 * y0
      a += cross
      cx += (x0 + x1) * cross
      cy += (y0 + y1) * cross
    }
    prev = point
  }
  if (a === 0) return { area: 0, lon: ring[0]?.[0] ?? 0, lat: ring[0]?.[1] ?? 0 }
  return { area: Math.abs(a / 2), lon: cx / (3 * a), lat: cy / (3 * a) }
}

/** Where to anchor the zone's links to its towers: the centre of its largest part. */
export function zoneCentre(geometry: MultiPolygon): LatLng {
  const parts = geometry.coordinates.map((rings) => ringCentroid(rings[0] ?? []))
  const largest = parts.reduce(
    (best, p) => (p.area > best.area ? p : best),
    parts[0] ?? {
      area: 0,
      lon: 0,
      lat: 0,
    },
  )
  return [largest.lat, largest.lon]
}
