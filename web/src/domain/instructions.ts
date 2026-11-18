import type { TFunction } from 'i18next'
import type { RouteStep } from '../api/types'

type T = TFunction | ((key: string, opts?: Record<string, unknown>) => string)

/** What a driver reads on a sign: the road number, else its name, else the kind of road. */
export function roadLabel(road: RouteStep['road'], t: T): string {
  if (road.ref) return road.ref
  if (road.name) return road.name
  return road.fclass
    ? String(t(`roadType.${road.fclass}`, { defaultValue: t('roadType.road') }))
    : String(t('roadType.road'))
}

export function instruction(step: Pick<RouteStep, 'kind' | 'road'>, t: T): string {
  return String(t(`guide.step.${step.kind}`, { road: roadLabel(step.road, t) }))
}

/** 10 m steps below 1 km, 0.1 km below 10 km, whole km beyond. */
export function formatDistance(m: number, lang: string): string {
  if (m < 1000) return `${Math.max(10, Math.round(m / 10) * 10)} m`
  const km = m / 1000
  const digits = km < 10 ? 1 : 0
  return `${km.toLocaleString(lang, { minimumFractionDigits: digits, maximumFractionDigits: digits })} km`
}
