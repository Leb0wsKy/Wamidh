import { describe, expect, it } from 'vitest'
import type { Incident } from '../api/types'
import {
  activeMission,
  dispatchOrder,
  endedAt,
  upsertIncident,
  incidentBadge,
  crewActions,
  crewCard,
  crewBoard,
  isOpen,
  mergeIncident,
  newSpreads,
} from './incident'

describe('crewActions', () => {
  it('walks a crew through the lifecycle one step at a time', () => {
    expect(crewActions('ACKNOWLEDGED')).toEqual(['EN_ROUTE', 'FALSE_ALARM'])
    expect(crewActions('EN_ROUTE')).toEqual(['ON_SITE', 'FALSE_ALARM'])
    expect(crewActions('ON_SITE')).toEqual(['UNDER_CONTROL', 'FALSE_ALARM'])
    expect(crewActions('UNDER_CONTROL')).toEqual(['CLOSED'])
  })

  it('offers nothing before acknowledgement or after closure', () => {
    for (const s of ['NEW', 'STATION_NOTIFIED', 'CLOSED', 'FALSE_ALARM'] as const) {
      expect(crewActions(s)).toEqual([])
    }
  })
})

describe('crewCard', () => {
  it('before arrival: Go, and false alarm only', () => {
    expect(crewCard('ACKNOWLEDGED')).toEqual({ go: true, actions: ['FALSE_ALARM'] })
    expect(crewCard('EN_ROUTE')).toEqual({ go: true, actions: ['FALSE_ALARM'] })
  })

  it('on site: no Go and no false alarm, only under control; then close', () => {
    expect(crewCard('ON_SITE')).toEqual({ go: false, actions: ['UNDER_CONTROL'] })
    expect(crewCard('UNDER_CONTROL')).toEqual({ go: false, actions: ['CLOSED'] })
  })

  it('offers nothing before acknowledgement or after closure', () => {
    for (const s of ['NEW', 'STATION_NOTIFIED', 'CLOSED', 'FALSE_ALARM'] as const) {
      expect(crewCard(s)).toEqual({ go: false, actions: [] })
    }
  })
})

describe('isOpen', () => {
  it('is false only for closed and false-alarm incidents', () => {
    expect(isOpen('ON_SITE')).toBe(true)
    expect(isOpen('CLOSED')).toBe(false)
    expect(isOpen('FALSE_ALARM')).toBe(false)
  })
})

describe('newSpreads', () => {
  const inc = (id: number, spreadNodes: number[]) =>
    ({
      id,
      status: 'ACKNOWLEDGED',
      events: [
        { ts: 't', type: 'node_fire', payload: { node_id: 1 } },
        ...spreadNodes.map((n) => ({ ts: 't', type: 'fire_spread', payload: { node_id: n } })),
      ],
    }) as unknown as Incident

  it('reports only spreads not seen before, then remembers them', () => {
    const seen = new Set<string>()
    expect(newSpreads(seen, [inc(1, [2])])).toEqual([{ incidentId: 1, nodeId: 2 }])
    expect(newSpreads(seen, [inc(1, [2])])).toEqual([])
    expect(newSpreads(seen, [inc(1, [2, 4])])).toEqual([{ incidentId: 1, nodeId: 4 }])
  })
})

describe('crewBoard', () => {
  const inc = (id: number, status: string, assigned_crew: number | null) =>
    ({ id, status, assigned_crew, events: [], node_ids: [id] }) as unknown as Incident

  it('sorts every live fire for a crew: mine, available, taken by others, awaiting the station', () => {
    const board = crewBoard(
      [
        inc(1, 'EN_ROUTE', 2),
        inc(2, 'ACKNOWLEDGED', null),
        inc(3, 'ON_SITE', 1),
        inc(4, 'STATION_NOTIFIED', null),
        inc(5, 'ACKNOWLEDGED', null),
      ],
      1,
    )

    expect(board.mine.map((i) => i.id)).toEqual([3])
    expect(board.available.map((i) => i.id)).toEqual([2, 5])
    expect(board.takenByOthers.map((i) => i.id)).toEqual([1])
    expect(board.awaitingStation.map((i) => i.id)).toEqual([4])
  })
})

describe('mergeIncident', () => {
  const inc = (id: number, status: string) => ({ id, status }) as unknown as Incident

  it('keeps open incidents newest first when a live update arrives', () => {
    const list = [inc(14, 'STATION_NOTIFIED'), inc(13, 'ON_SITE')]

    expect(mergeIncident(list, inc(15, 'STATION_NOTIFIED')).map((i) => i.id)).toEqual([15, 14, 13])
  })

  it('removes an incident once it is closed or a false alarm', () => {
    const list = [inc(14, 'ACKNOWLEDGED'), inc(13, 'UNDER_CONTROL')]

    expect(mergeIncident(list, inc(13, 'CLOSED')).map((i) => i.id)).toEqual([14])
    expect(mergeIncident(list, inc(14, 'FALSE_ALARM')).map((i) => i.id)).toEqual([13])
  })
})

describe('activeMission', () => {
  const inc = (id: number, status: string) => ({ id, status }) as unknown as Incident

  it('opens the mission still burning, not one already under control', () => {
    expect(activeMission([inc(9, 'UNDER_CONTROL'), inc(8, 'EN_ROUTE')], null)?.id).toBe(8)
  })

  it('opens the one the crew tapped, if it is still theirs', () => {
    const mine = [inc(9, 'EN_ROUTE'), inc(8, 'UNDER_CONTROL')]
    expect(activeMission(mine, 8)?.id).toBe(8)
    expect(activeMission(mine, 42)?.id).toBe(9)
  })

  it('falls back to the newest, and to nothing without missions', () => {
    expect(activeMission([inc(9, 'UNDER_CONTROL'), inc(8, 'UNDER_CONTROL')], null)?.id).toBe(9)
    expect(activeMission([], null)).toBeNull()
  })
})

describe('dispatchOrder', () => {
  const inc = (id: number, status: string) => ({ id, status }) as unknown as Incident

  it('lists fires still burning first (newest first), then those under control', () => {
    const order = dispatchOrder([
      inc(3, 'UNDER_CONTROL'),
      inc(5, 'EN_ROUTE'),
      inc(4, 'STATION_NOTIFIED'),
      inc(6, 'UNDER_CONTROL'),
    ])
    expect(order.map((i) => i.id)).toEqual([5, 4, 6, 3])
  })
})

describe('incidentBadge', () => {
  const inc = (status: string) => ({ status }) as unknown as Incident

  it('counts fires still burning; urgent while one waits for the station', () => {
    expect(incidentBadge([inc('UNDER_CONTROL')])).toEqual({ count: 0, urgent: false })
    expect(incidentBadge([inc('EN_ROUTE'), inc('UNDER_CONTROL')])).toEqual({
      count: 1,
      urgent: false,
    })
    expect(incidentBadge([inc('EN_ROUTE'), inc('NEW')])).toEqual({ count: 2, urgent: true })
  })
})

describe('endedAt', () => {
  it('is when the crew reported the fire under control, else null (still burning)', () => {
    const base = { id: 1, events: [] } as unknown as Incident
    const settled = {
      ...base,
      status: 'UNDER_CONTROL',
      events: [
        { ts: '2026-10-01T12:00:00Z', type: 'node_fire', payload: {} },
        { ts: '2026-10-01T12:40:00Z', type: 'status', payload: { status: 'UNDER_CONTROL' } },
      ],
    } as Incident
    expect(endedAt(settled)).toBe(Date.parse('2026-10-01T12:40:00Z'))
    expect(endedAt({ ...base, status: 'EN_ROUTE' } as Incident)).toBeNull()
  })
})

describe('history of past incidents', () => {
  const inc = (id: number, status: string, events: unknown[] = []) =>
    ({ id, status, events }) as unknown as Incident

  it('lists burning fires, then those under control, then closed ones (each newest first)', () => {
    const order = dispatchOrder([
      inc(1, 'CLOSED'),
      inc(5, 'EN_ROUTE'),
      inc(3, 'FALSE_ALARM'),
      inc(4, 'UNDER_CONTROL'),
      inc(2, 'CLOSED'),
    ])
    expect(order.map((i) => i.id)).toEqual([5, 4, 3, 2, 1])
  })

  it('keeps closed incidents when a live update arrives, replacing the previous version', () => {
    const list = [inc(2, 'CLOSED'), inc(3, 'EN_ROUTE')]

    const next = upsertIncident(list, inc(3, 'CLOSED'))

    expect(next.map((i) => [i.id, i.status])).toEqual([
      [3, 'CLOSED'],
      [2, 'CLOSED'],
    ])
  })

  it('a closed fire ended when it was brought under control, else when it was closed', () => {
    const ev = (ts: string, status: string) => ({ ts, type: 'status', payload: { status } })
    const controlled = inc(1, 'CLOSED', [
      ev('2026-10-01T12:40:00Z', 'UNDER_CONTROL'),
      ev('2026-10-01T13:10:00Z', 'CLOSED'),
    ])
    const falseAlarm = inc(2, 'FALSE_ALARM', [ev('2026-10-01T12:05:00Z', 'FALSE_ALARM')])

    expect(endedAt(controlled)).toBe(Date.parse('2026-10-01T12:40:00Z'))
    expect(endedAt(falseAlarm)).toBe(Date.parse('2026-10-01T12:05:00Z'))
  })
})
