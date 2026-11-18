import { useEffect, useState } from 'react'

/** Time since an event as m:ss (h:mm:ss past an hour): how long a fire has been burning. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = String(total % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

// ASSUMPTION: single Li-ion cell behind the node's regulator, 3.3 V treated as empty (the
// ESP32 browns out below) and 4.2 V as full. Linear between, which is coarse for Li-ion
// discharge curves; the gauge is indicative and always shown with the measured voltage.
const EMPTY_V = 3.3
const FULL_V = 4.2

export function batteryLevel(volts: number | null): number | null {
  if (volts === null) return null
  return Math.min(1, Math.max(0, (volts - EMPTY_V) / (FULL_V - EMPTY_V)))
}

export interface TimeUnits {
  s: string
  min: string
  h: string
  d: string
}
const LATIN_UNITS: TimeUnits = { s: 's', min: 'min', h: 'h', d: 'd' }

/** "8 s", "5 min", "3 h", "2 d": how long ago, short, in the interface language's units. */
export function shortAgo(ms: number, units: TimeUnits = LATIN_UNITS): string {
  const s = Math.max(0, Math.round(ms / 1000))
  if (s < 120) return `${s} ${units.s}`
  if (s < 120 * 60) return `${Math.round(s / 60)} ${units.min}`
  if (s < 48 * 3600) return `${Math.round(s / 3600)} ${units.h}`
  return `${Math.round(s / 86400)} ${units.d}`
}

/** Current time, refreshed every second (live counters). */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])
  return now
}

/** The interface language's short time units (locale key `units`). */
export function timeUnits(t: (key: string) => string): TimeUnits {
  return { s: t('units.s'), min: t('units.min'), h: t('units.h'), d: t('units.d') }
}
