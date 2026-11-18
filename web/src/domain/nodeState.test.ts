import { describe, expect, it } from 'vitest'
import { NODE_STATES, bySeverity, nodeStyle } from './nodeState'

describe('nodeStyle', () => {
  it('gives every state a distinct colour and a label key', () => {
    const colours = NODE_STATES.map((s) => nodeStyle(s).color)
    expect(new Set(colours).size).toBe(NODE_STATES.length)
    for (const s of NODE_STATES) expect(nodeStyle(s).labelKey).toBe(`nodeState.${s}`)
  })

  it('uses status colours: green normal, yellow alert, red fire, grey offline', () => {
    expect(nodeStyle('NORMAL').color).toBe('#2E8B3E')
    expect(nodeStyle('ALERT').color).toBe('#E3B505')
    expect(nodeStyle('OFFLINE').color).toBe('#8C8C8C')
  })

  it('uses the Wamidh accent for fire and pulses only fire', () => {
    expect(nodeStyle('FIRE').color).toBe('#B3261E')
    expect(NODE_STATES.filter((s) => nodeStyle(s).pulse)).toEqual(['FIRE'])
  })
})

describe('bySeverity', () => {
  it('puts fires first and healthy nodes last', () => {
    const sorted = [...NODE_STATES].sort(bySeverity)
    expect(sorted).toEqual(['FIRE', 'LOST_PROBABLY_BURNED', 'ALERT', 'OFFLINE', 'NORMAL'])
  })
})
