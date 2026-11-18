// Turn-by-turn guidance on a route from the backend (contracts/api.md, Route): where the
// vehicle is along the road, the next manoeuvre, what is left to drive and walk. Pure
// functions, so the navigation screen only feeds them GPS fixes.

import type { LonLat, NavRoute, RouteStep } from '../api/types'

// ASSUMPTION: walking speed on a forest slope carrying equipment (~4 km/h), not measured.
const WALK_M_PER_S = 1.1
/** the access point counts as reached within this distance */
const AT_ACCESS_M = 30
/** the node counts as reached within this distance (GPS accuracy under trees) */
const AT_NODE_M = 20
/** with a previous position, first look for the vehicle on this stretch of road */
const BEHIND_M = 200
const AHEAD_M = 2000
const TRUST_HINT_M = 50

// ASSUMPTION: speed from an off-road start (yard, field, wrong track) back to the road.
const JOIN_M_PER_S = 15 / 3.6
/** look this far ahead on the road to orient the map */
const HEADING_LOOKAHEAD_M = 30

const R = 6_371_008.8
const RAD = Math.PI / 180

export interface PreparedRoute {
  route: NavRoute
  /** local metric projection (equirectangular, fine over a few tens of km) */
  xy: (p: LonLat) => [number, number]
  points: [number, number][]
  /** distance from the start to each vertex of the drive geometry */
  cum: number[]
  /** distance from the start to each step's manoeuvre */
  stepAt: number[]
}

export interface Progress {
  phase: 'drive' | 'walk' | 'arrived'
  /** distance from the start of the drive to the projected position */
  alongM: number
  /** distance between the fix and the road (drive phase) */
  offRouteM: number
  /** the next manoeuvre (drive) or null (walk, arrived) */
  next: RouteStep | null
  /** distance to the next manoeuvre, or to the node when walking */
  toNextM: number
  /** drive left + walk */
  remainingM: number
  remainingS: number
}

export function prepare(input: NavRoute): PreparedRoute {
  const o = input.origin
  const kx = RAD * R * Math.cos(o.lat * RAD)
  const xy = (p: LonLat): [number, number] => [(p.lon - o.lon) * kx, (p.lat - o.lat) * RAD * R]
  // The backend starts the drive at the nearest road; the way from the vehicle to that road
  // (station yard, or where a wrong turn ended) is part of the route too.
  const route = joinFromOrigin(input, xy)
  const points = route.drive.geometry.map(([lon, lat]) => xy({ lon, lat }))
  const cum = [0]
  for (let i = 1; i < points.length; i++) {
    cum.push(cum[i - 1]! + dist(points[i - 1]!, points[i]!))
  }
  // Each step's location is a vertex of the geometry; match them in order.
  const stepAt: number[] = []
  let j = 0
  for (const s of route.drive.steps) {
    const [x, y] = xy({ lon: s.location[0], lat: s.location[1] })
    let best = j
    for (let k = j; k < points.length; k++) {
      if (dist(points[k]!, [x, y]) < dist(points[best]!, [x, y])) best = k
      if (dist(points[k]!, [x, y]) < 0.5) break
    }
    j = best
    stepAt.push(cum[best] ?? 0)
  }
  return { route, xy, points, cum, stepAt }
}

/**
 * Where a GPS fix is on the route. `lastAlongM` (the previous result) keeps the vehicle
 * on the right stretch where a mountain road doubles back close to itself.
 */
export function progress(nav: PreparedRoute, pos: LonLat, lastAlongM?: number): Progress {
  const { route, cum } = nav
  const here = nav.xy(pos)
  const total = cum[cum.length - 1] ?? 0

  let snap = nearest(nav, here, 0, Infinity)
  if (lastAlongM !== undefined) {
    const local = nearest(nav, here, lastAlongM - BEHIND_M, lastAlongM + AHEAD_M)
    if (local.d <= TRUST_HINT_M) snap = local
  }
  const toNode = dist(here, nav.xy(route.target))
  const walkS = (m: number) => m / WALK_M_PER_S

  if (toNode <= AT_NODE_M) {
    return {
      phase: 'arrived',
      alongM: total,
      offRouteM: 0,
      next: null,
      toNextM: 0,
      remainingM: 0,
      remainingS: 0,
    }
  }
  const driveLeft = Math.max(0, total - snap.along)
  if (driveLeft <= AT_ACCESS_M) {
    return {
      phase: 'walk',
      alongM: snap.along,
      offRouteM: snap.d,
      next: null,
      toNextM: toNode,
      remainingM: toNode,
      remainingS: walkS(toNode),
    }
  }
  const k = nav.stepAt.findIndex((at) => at > snap.along + 5)
  const next = k >= 0 ? route.drive.steps[k]! : null
  const walkM = route.walk.distance_m
  return {
    phase: 'drive',
    alongM: snap.along,
    offRouteM: snap.d,
    next,
    toNextM: k >= 0 ? nav.stepAt[k]! - snap.along : driveLeft,
    remainingM: driveLeft + walkM,
    remainingS: (total > 0 ? route.drive.duration_s * (driveLeft / total) : 0) + walkS(walkM),
  }
}

function joinFromOrigin(route: NavRoute, xy: (p: LonLat) => [number, number]): NavRoute {
  const first = route.drive.geometry[0]
  if (!first) return route
  const gap = dist(xy(route.origin), xy({ lon: first[0], lat: first[1] }))
  if (gap < 1) return route
  return {
    ...route,
    drive: {
      ...route.drive,
      geometry: [[route.origin.lon, route.origin.lat], ...route.drive.geometry],
      distance_m: route.drive.distance_m + gap,
      duration_s: route.drive.duration_s + gap / JOIN_M_PER_S,
    },
  }
}

/** Direction of travel along the road at `alongM`, degrees clockwise from north. */
export function headingAt(nav: PreparedRoute, alongM: number): number {
  const total = nav.cum[nav.cum.length - 1] ?? 0
  const from = Math.max(0, Math.min(alongM, total - HEADING_LOOKAHEAD_M))
  const [x1, y1] = nav.xy(pointAlong(nav, from))
  const [x2, y2] = nav.xy(pointAlong(nav, Math.min(total, from + HEADING_LOOKAHEAD_M)))
  return bearing(x2 - x1, y2 - y1)
}

/** Direction from one position to another, degrees clockwise from north. */
export function headingTo(nav: PreparedRoute, a: LonLat, b: LonLat): number {
  const [x1, y1] = nav.xy(a)
  const [x2, y2] = nav.xy(b)
  return bearing(x2 - x1, y2 - y1)
}

function bearing(dx: number, dy: number): number {
  return ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360
}

/** The position `alongM` metres from the start of the drive (demo playback). */
export function pointAlong(nav: PreparedRoute, alongM: number): LonLat {
  const g = nav.route.drive.geometry
  const { cum } = nav
  for (let i = 1; i < g.length; i++) {
    if (cum[i]! >= alongM) {
      const f = (alongM - cum[i - 1]!) / (cum[i]! - cum[i - 1]! || 1)
      const [lon1, lat1] = g[i - 1]!
      const [lon2, lat2] = g[i]!
      return { lon: lon1 + f * (lon2 - lon1), lat: lat1 + f * (lat2 - lat1) }
    }
  }
  const [lon, lat] = g[g.length - 1]!
  return { lon, lat }
}

/**
 * Demo playback: where the crew would be `seconds` after leaving, driving at the route's
 * average speed and then walking. Only for rehearsing without a vehicle; the navigation
 * screen labels it as a simulation.
 */
export function simulatedPosition(nav: PreparedRoute, seconds: number): LonLat {
  const { drive, walk } = nav.route
  const total = nav.cum[nav.cum.length - 1] ?? 0
  if (seconds < drive.duration_s) return pointAlong(nav, (total * seconds) / drive.duration_s)
  const walked = (seconds - drive.duration_s) * WALK_M_PER_S
  const f = walk.distance_m > 0 ? Math.min(1, walked / walk.distance_m) : 1
  const [a, b] = [walk.geometry[0]!, walk.geometry[walk.geometry.length - 1]!]
  return f >= 1
    ? { lon: b[0], lat: b[1] }
    : { lon: a[0] + f * (b[0] - a[0]), lat: a[1] + f * (b[1] - a[1]) }
}

function dist(a: [number, number], b: [number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1])
}

/** Closest point of the polyline, among segments overlapping [from, to] metres. */
function nearest(
  nav: PreparedRoute,
  p: [number, number],
  from: number,
  to: number,
): { along: number; d: number } {
  const { points, cum } = nav
  let best = { along: 0, d: Infinity }
  for (let i = 1; i < points.length; i++) {
    if (cum[i]! < from || cum[i - 1]! > to) continue
    const a = points[i - 1]!
    const b = points[i]!
    const len = cum[i]! - cum[i - 1]!
    const t = len
      ? Math.max(
          0,
          Math.min(1, ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / len ** 2),
        )
      : 0
    const d = dist(p, [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])])
    if (d < best.d) best = { along: cum[i - 1]! + t * len, d }
  }
  // A one-point route has no segment.
  if (best.d === Infinity && points.length) best = { along: 0, d: dist(p, points[0]!) }
  return best
}
