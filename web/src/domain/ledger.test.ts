import { describe, expect, it } from 'vitest'
import type { SensorNode } from '../api/types'
import { sensor } from '../test/fixtures'
import { ledgerRows } from './ledger'

const risk = (id: number, p: number, extra: Partial<SensorNode> = {}) =>
  sensor(id, { risk_percentile: p, ...extra })

describe('ledgerRows', () => {
  const fleet = Array.from({ length: 30 }, (_, i) => risk(i + 1, 50 + i)) // 30 has the top risk

  it('without a search: the highest-risk sensors, up to the limit', () => {
    const { rows, total } = ledgerRows(fleet, '', 10)

    expect(rows.map((n) => n.id)).toEqual([30, 29, 28, 27, 26, 25, 24, 23, 22, 21])
    expect(total).toBe(30)
  })

  it('puts sensors in alarm first, fire on top, and never cuts them off', () => {
    const nodes = [
      ...fleet,
      risk(40, 1, { state: 'ALERT' }),
      risk(41, 2, { state: 'FIRE' }),
      risk(42, 3, { state: 'OFFLINE' }),
    ]

    const ids = ledgerRows(nodes, '', 2).rows.map((n) => n.id)

    expect(ids).toEqual([41, 40, 42])
  })

  it('fills the rest of the list with the highest-risk calm sensors', () => {
    const nodes = [...fleet, risk(41, 2, { state: 'FIRE' })]

    expect(ledgerRows(nodes, '', 3).rows.map((n) => n.id)).toEqual([41, 30, 29])
  })

  it('searches by number: the exact sensor first, then numbers starting with it', () => {
    const { rows, total } = ledgerRows(fleet, '2', 5)

    expect(rows.map((n) => n.id)).toEqual([2, 20, 21, 22, 23])
    expect(total).toBe(11) // 2 and 20–29
  })

  it('ignores spaces and a leading #, and finds nothing for an unknown number', () => {
    expect(ledgerRows(fleet, ' #12 ', 10).rows.map((n) => n.id)).toEqual([12])
    expect(ledgerRows(fleet, '999', 10)).toEqual({ rows: [], total: 0 })
  })
})
