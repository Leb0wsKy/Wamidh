// Reading the fire spread forecast (ADR 0004) for people: directions, confidence, times.

const COMPASS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'] as const
export type CompassPoint = (typeof COMPASS)[number]

/** Forecast horizons offered by the time slider, in fire minutes from now. */
export const HORIZONS = [0, 15, 30, 60, 120] as const
export type Horizon = (typeof HORIZONS)[number]

/** The nearest of the eight compass points to a bearing (degrees from north, clockwise). */
export function compassPoint(deg: number): CompassPoint {
  const i = Math.round((((deg % 360) + 360) % 360) / 45) % 8
  return COMPASS[i]!
}

/** How much of the ensemble still agrees with what the sensors saw (effective sample size). */
export function confidenceLevel(essRatio: number): 'high' | 'medium' | 'low' {
  if (essRatio >= 0.5) return 'high'
  if (essRatio >= 0.15) return 'medium'
  return 'low'
}

/** Clock seconds to fire minutes: a demo fire runs `timeScale` times faster than the clock. */
export function toFireMinutes(clockSeconds: number, timeScale: number): number {
  return (clockSeconds / 60) * timeScale
}

/** "~43 min", "~2 h 15", "< 1 min" for an expected arrival in fire minutes. */
export function etaLabel(minutes: number | null): string {
  if (minutes === null) return '—'
  if (minutes < 1) return '< 1 min'
  const m = Math.round(minutes)
  if (m < 60) return `~${m} min`
  return `~${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')}`
}
