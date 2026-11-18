import { READING_TONES as T } from '../config'

export type Tone = 'normal' | 'alert' | 'fire'
export type ReadingKind = 'temp' | 'rh' | 'gas' | 'ai' | 'flame'

/** How strongly a single reading points to fire, for its colour on screen. */
export function readingTone(kind: ReadingKind, value: number | boolean | null | undefined): Tone {
  if (value == null) return 'normal'
  if (kind === 'flame') return value ? 'fire' : 'normal'
  const v = Number(value)
  switch (kind) {
    case 'temp':
      return v >= T.temp.fire ? 'fire' : v >= T.temp.alert ? 'alert' : 'normal'
    case 'rh':
      return v <= T.rh.alert ? 'alert' : 'normal'
    case 'gas':
      return v < T.gas.fire ? 'fire' : v < T.gas.alert ? 'alert' : 'normal'
    case 'ai':
      return v >= T.ai.fire ? 'fire' : v >= T.ai.alert ? 'alert' : 'normal'
  }
}
