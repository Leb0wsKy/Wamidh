import type { NodeState } from '../api/types'

export const NODE_STATES: readonly NodeState[] = [
  'NORMAL',
  'ALERT',
  'FIRE',
  'OFFLINE',
  'LOST_PROBABLY_BURNED',
]

export interface NodeStyle {
  color: string
  labelKey: string
  /** fires pulse so they catch the eye on a busy map */
  pulse: boolean
}

// Status colours: green = healthy, yellow = alert, red = fire (Wamidh accent), grey = not
// heard, near-black = lost in a fire. Colour is never alone: markers carry a tooltip and the
// side panel names every state.
const COLORS: Record<NodeState, string> = {
  NORMAL: '#2E8B3E',
  ALERT: '#E3B505',
  FIRE: '#B3261E',
  OFFLINE: '#8C8C8C',
  LOST_PROBABLY_BURNED: '#1a1a19',
}

const SEVERITY: Record<NodeState, number> = {
  FIRE: 0,
  LOST_PROBABLY_BURNED: 1,
  ALERT: 2,
  OFFLINE: 3,
  NORMAL: 4,
}

export function nodeStyle(state: NodeState): NodeStyle {
  return { color: COLORS[state], labelKey: `nodeState.${state}`, pulse: state === 'FIRE' }
}

export function bySeverity(a: NodeState, b: NodeState): number {
  return SEVERITY[a] - SEVERITY[b]
}
