// Client for the Wamidh backend (contracts/api.md): REST for reads and actions, one
// WebSocket for live events. The socket reconnects by itself and reports its state, so the
// station sees "connection lost" instead of a silently frozen map.

import type {
  AlertProposal,
  AlertZone,
  CellTower,
  Crew,
  FeatureCollection,
  Forecast,
  PublicAlert,
  EmberApi,
  Gateway,
  History,
  Incident,
  IncidentStatus,
  LiveEvent,
  LonLat,
  NavRoute,
  RiskOverlay,
  SensorNode,
  Station,
} from './types'

interface Options {
  base: string
  wsUrl: string
  fetch?: typeof fetch
  WebSocket?: typeof WebSocket
  reconnectMs?: number
}

export class HttpApi implements EmberApi {
  private readonly base: string
  private readonly wsUrl: string
  private readonly fetchImpl: typeof fetch
  private readonly WS: typeof WebSocket
  private readonly reconnectMs: number
  private readonly listeners = new Set<(e: LiveEvent) => void>()
  private readonly connectionListeners = new Set<(up: boolean) => void>()
  private socket: WebSocket | null = null
  private up = false

  constructor(opts: Options) {
    this.base = opts.base
    this.wsUrl = opts.wsUrl
    this.fetchImpl = opts.fetch ?? fetch.bind(globalThis)
    this.WS = opts.WebSocket ?? WebSocket
    this.reconnectMs = opts.reconnectMs ?? 2000
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await (init
      ? this.fetchImpl(`${this.base}${path}`, init)
      : this.fetchImpl(`${this.base}${path}`))
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}))
      throw new Error((detail as { detail?: string }).detail ?? `HTTP ${res.status} on ${path}`)
    }
    return (await res.json()) as T
  }

  listNodes(): Promise<SensorNode[]> {
    return this.request('/nodes')
  }

  listGateways(): Promise<Gateway[]> {
    return this.request('/gateways')
  }

  listIncidents(): Promise<Incident[]> {
    return this.request('/incidents')
  }

  riskOverlay(): Promise<RiskOverlay> {
    return this.request('/risk-map')
  }

  history(minutes: number, nodeIds?: number[]): Promise<History> {
    const only = nodeIds ? `&nodes=${nodeIds.join(',')}` : ''
    return this.request(`/history?minutes=${minutes}${only}`)
  }

  listStations(): Promise<Station[]> {
    return this.request('/stations')
  }

  listCrews(): Promise<Crew[]> {
    return this.request('/crews')
  }

  assign(incidentId: number, crewId: number): Promise<Incident> {
    return this.request(`/incidents/${incidentId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ crew_id: crewId }),
    })
  }

  acknowledge(incidentId: number): Promise<Incident> {
    return this.request(`/incidents/${incidentId}/ack`, { method: 'POST' })
  }

  setStatus(incidentId: number, status: IncidentStatus, crewId: number): Promise<Incident> {
    return this.request(`/incidents/${incidentId}/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, crew_id: crewId }),
    })
  }

  route(incidentId: number, opts: { from?: LonLat; crewId?: number }): Promise<NavRoute> {
    const q = new URLSearchParams()
    if (opts.from) q.set('from', `${opts.from.lat},${opts.from.lon}`)
    if (opts.crewId !== undefined) q.set('crew_id', String(opts.crewId))
    const qs = q.toString()
    return this.request(`/incidents/${incidentId}/route${qs ? `?${qs}` : ''}`)
  }

  forecast(incidentId: number): Promise<Forecast> {
    return this.request(`/incidents/${incidentId}/forecast`)
  }

  listZones(): Promise<FeatureCollection<AlertZone>> {
    return this.request('/zones')
  }

  listTowers(): Promise<FeatureCollection<CellTower>> {
    return this.request('/towers')
  }

  alertProposal(incidentId: number): Promise<AlertProposal> {
    return this.request(`/incidents/${incidentId}/alert-proposal`)
  }

  sendAlert(incidentId: number, confirmedBy: string): Promise<{ id: number; created_at: string }> {
    return this.request(`/incidents/${incidentId}/alert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirmed_by: confirmedBy }),
    })
  }

  listAlerts(activeOnly: boolean): Promise<PublicAlert[]> {
    return this.request(`/alerts${activeOnly ? '?active=true' : ''}`)
  }

  subscribe(listener: (event: LiveEvent) => void): () => void {
    this.listeners.add(listener)
    this.connect()
    return () => this.listeners.delete(listener)
  }

  onConnection(listener: (up: boolean) => void): () => void {
    this.connectionListeners.add(listener)
    return () => this.connectionListeners.delete(listener)
  }

  private setUp(up: boolean): void {
    if (up === this.up) return
    this.up = up
    for (const l of this.connectionListeners) l(up)
  }

  private connect(): void {
    if (this.socket) return
    const ws = new this.WS(this.wsUrl)
    this.socket = ws
    ws.onopen = () => this.setUp(true)
    ws.onmessage = (msg: MessageEvent<string> | { data: string }) => {
      const event = JSON.parse(msg.data) as LiveEvent
      for (const l of this.listeners) l(event)
    }
    ws.onclose = () => {
      this.socket = null
      this.setUp(false)
      setTimeout(() => this.connect(), this.reconnectMs)
    }
  }
}
