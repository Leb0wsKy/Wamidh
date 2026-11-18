import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HttpApi } from './http'
import type { LiveEvent } from './types'

class FakeSocket {
  static instances: FakeSocket[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  url: string
  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }
  close() {
    this.onclose?.()
  }
  send() {}
}

const nodeJson = {
  id: 1,
  lon: 8.62,
  lat: 36.71,
  state: 'NORMAL',
  last_seen: '2026-07-20T14:00:00Z',
  battery_v: 4.0,
  risk_percentile: 99.4,
  gateway_id: 35,
  readings: { temp_c: 31 },
  link: { received: 5, lost: 0, rejected: 0 },
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

function api() {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => ({
    ok: true,
    status: 200,
    json: async () => (url.endsWith('/nodes') ? [nodeJson] : { url, method: init?.method }),
  }))
  const a = new HttpApi({
    base: '/api/v1',
    wsUrl: 'ws://test/api/v1/ws',
    fetch: fetchMock as unknown as typeof fetch,
    WebSocket: FakeSocket as unknown as typeof WebSocket,
  })
  return { a, fetchMock }
}

describe('HttpApi', () => {
  it('lists nodes from the backend', async () => {
    const { a } = api()

    const nodes = await a.listNodes()

    expect(nodes[0]).toMatchObject({ id: 1, state: 'NORMAL', link: { received: 5 } })
  })

  it('acknowledges with a POST', async () => {
    const { a, fetchMock } = api()

    await a.acknowledge(4)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/incidents/4/ack', { method: 'POST' })
  })

  it('lets a crew take an incident and sends its id with status updates', async () => {
    const { a, fetchMock } = api()

    await a.assign(4, 2)
    await a.setStatus(4, 'EN_ROUTE', 2)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/incidents/4/assign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crew_id: 2 }),
    })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/incidents/4/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'EN_ROUTE', crew_id: 2 }),
    })
  })

  it('broadcasts a public alert with who confirmed it, and lists active alerts', async () => {
    const { a, fetchMock } = api()

    await a.sendAlert(4, 'dispatcher')
    await a.listAlerts(true)

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/incidents/4/alert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed_by: 'dispatcher' }),
    })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/alerts?active=true')
  })

  it('asks for a route from the live position, or from the crew station', async () => {
    const { a, fetchMock } = api()

    await a.route(4, { from: { lat: 36.79, lon: 8.69 } })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/incidents/4/route?from=36.79%2C8.69')
    await a.route(4, { crewId: 2 })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/v1/incidents/4/route?crew_id=2')
  })

  it('delivers live events and reports the connection state', () => {
    const { a } = api()
    const events: LiveEvent[] = []
    const states: boolean[] = []
    a.onConnection((up) => states.push(up))
    a.subscribe((e) => events.push(e))

    const ws = FakeSocket.instances[0]!
    ws.onopen?.()
    ws.onmessage?.({ data: JSON.stringify({ kind: 'node', node: nodeJson }) })

    expect(events).toHaveLength(1)
    expect(states).toEqual([true])
  })

  it('reconnects by itself after the connection drops', () => {
    const { a } = api()
    const states: boolean[] = []
    a.onConnection((up) => states.push(up))
    a.subscribe(() => {})
    FakeSocket.instances[0]!.onopen?.()

    FakeSocket.instances[0]!.close()
    vi.advanceTimersByTime(3000)

    expect(states).toEqual([true, false])
    expect(FakeSocket.instances).toHaveLength(2)
  })
})
