import { describe, expect, it } from 'vitest'
import { nodeIcon, setHighlight } from './mapIcons'

describe('nodeIcon', () => {
  it('returns the same icon object for the same sensor and state', () => {
    // A new object makes react-leaflet replace the marker's DOM element. If that happens
    // between mousedown and mouseup (live re-render, hover), the browser fires no click.
    expect(nodeIcon(2, 'NORMAL')).toBe(nodeIcon(2, 'NORMAL'))
  })

  it('changes only when the state changes', () => {
    expect(nodeIcon(2, 'FIRE')).not.toBe(nodeIcon(2, 'NORMAL'))
    expect(nodeIcon(2, 'FIRE').options.html).toContain('data-state="FIRE"')
  })
})

describe('compact sensor dots', () => {
  it('draws a small dot without a number, cached like the full icon', () => {
    const dot = nodeIcon(2, 'NORMAL', true)

    expect(dot).toBe(nodeIcon(2, 'NORMAL', true))
    expect(dot).not.toBe(nodeIcon(2, 'NORMAL'))
    expect(dot.options.html).toContain('eg-node-dot')
    expect(dot.options.html).not.toContain('>2<')
    expect(dot.options.iconSize).toEqual([12, 12])
  })
})

describe('setHighlight', () => {
  it('marks the existing marker element instead of swapping its icon', () => {
    const marker = document.createElement('div')
    marker.innerHTML = '<div class="eg-node" data-state="NORMAL">2</div>'
    const disc = marker.firstElementChild!

    setHighlight(marker, true)
    expect(disc.hasAttribute('data-highlight')).toBe(true)
    expect(marker.firstElementChild).toBe(disc) // same element: a click in progress survives

    setHighlight(marker, false)
    expect(disc.hasAttribute('data-highlight')).toBe(false)
    setHighlight(undefined, true) // marker not on the map yet: nothing to do
  })
})
