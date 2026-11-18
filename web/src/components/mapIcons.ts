import L from 'leaflet'
import type { NodeState } from '../api/types'
import { nodeStyle } from '../domain/nodeState'

// One icon object per (sensor, state). react-leaflet replaces the marker's DOM element whenever
// it receives a new icon object; if that happens between mousedown and mouseup (live re-render
// every second, hover highlight), the browser fires no click and the user's click is lost.
const cache = new Map<string, L.DivIcon>()

/** A numbered disc in the state colour; fires are bigger and carry a pulsing ring. `compact`
 *  draws a small dot without the number, for 200 sensors seen from afar. */
export function nodeIcon(id: number, state: NodeState, compact = false): L.DivIcon {
  const key = `${id}|${state}|${compact ? 'dot' : 'disc'}`
  const hit = cache.get(key)
  if (hit) return hit
  const size = compact ? 12 : state === 'FIRE' ? 30 : 24
  const style = `background:${nodeStyle(state).color}`
  const icon = L.divIcon({
    className: '',
    html: compact
      ? `<div class="eg-node eg-node-dot" data-state="${state}" style="${style}"></div>`
      : `<div class="eg-node" data-state="${state}" style="${style}">${id}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
  cache.set(key, icon)
  return icon
}

/** Highlight a marker by marking its existing element, never by swapping its icon. */
export function setHighlight(markerElement: HTMLElement | undefined, on: boolean): void {
  markerElement?.querySelector('.eg-node')?.toggleAttribute('data-highlight', on)
}
