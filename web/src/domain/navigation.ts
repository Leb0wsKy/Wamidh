import type { LonLat } from '../api/types'

const EARTH_RADIUS_KM = 6371.0088

/** Great-circle distance in kilometres (haversine). */
export function distanceKm(a: LonLat, b: LonLat): number {
  const rad = Math.PI / 180
  const dLat = (b.lat - a.lat) * rad
  const dLon = (b.lon - a.lon) * rad
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h))
}

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const

/** 8-point compass direction from `a` to `b` (e.g. where the station is from the nodes). */
export function bearingLabel(a: LonLat, b: LonLat): (typeof COMPASS)[number] {
  const rad = Math.PI / 180
  const y = Math.sin((b.lon - a.lon) * rad) * Math.cos(b.lat * rad)
  const x =
    Math.cos(a.lat * rad) * Math.sin(b.lat * rad) -
    Math.sin(a.lat * rad) * Math.cos(b.lat * rad) * Math.cos((b.lon - a.lon) * rad)
  const deg = (Math.atan2(y, x) / rad + 360) % 360
  return COMPASS[Math.round(deg / 45) % 8]!
}
