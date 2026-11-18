// Mirrors contracts/api.md. Update the contract first, then this file.

export type NodeState = 'NORMAL' | 'ALERT' | 'FIRE' | 'OFFLINE' | 'LOST_PROBABLY_BURNED'

export interface LonLat {
  lon: number
  lat: number
}

export interface SensorNode extends LonLat {
  id: number
  state: NodeState
  last_seen: string | null
  battery_v: number | null
  risk_percentile: number | null
  /** null when no gateway has line of sight to the node */
  gateway_id: number | null
  /** last reported sensor values */
  readings?: {
    gas_ratio?: number
    temp_c?: number
    rh_pct?: number
    flame?: boolean
    fire_prob?: number
  }
  /** zone the node is responsible for (m); not its detection range */
  coverage_radius_m?: number
  /** radio link statistics kept by the backend */
  link?: { received: number; lost: number; rejected: number }
  last_alert_at?: string | null
  last_fire_at?: string | null
  access_point?: (LonLat & { road_type: string }) | null
}

export interface Gateway extends LonLat {
  id: number
  elevation_m: number
  nodes_assigned: number
}

export type IncidentStatus =
  | 'NEW'
  | 'STATION_NOTIFIED'
  | 'ACKNOWLEDGED'
  | 'EN_ROUTE'
  | 'ON_SITE'
  | 'UNDER_CONTROL'
  | 'CLOSED'
  | 'FALSE_ALARM'

export interface IncidentEvent {
  ts: string
  type: string
  payload: Record<string, unknown>
}

export interface Incident {
  id: number
  status: IncidentStatus
  first_node_id: number
  estimated_origin: LonLat | null
  created_at: string
  acknowledged_at: string | null
  access_point: (LonLat & { road_type: string }) | null
  /** sensors that detected this fire */
  node_ids: number[]
  /** crew that took the incident */
  assigned_crew: number | null
  /** audit log, oldest first */
  events: IncidentEvent[]
}

export interface Station extends LonLat {
  id: number
  name: string
  source?: string
}

export interface Crew {
  id: number
  name: string
  station_id: number
}

export interface RiskOverlay {
  url: string
  /** [[south, west], [north, east]] */
  bounds: [[number, number], [number, number]]
}

export type LiveEvent =
  | { kind: 'node'; node: SensorNode }
  | { kind: 'incident'; incident: Incident }
  | { kind: 'forecast'; incident_id: number; computed_at: string }

/** What every page needs from the backend (implemented by HttpApi). */
export type StepKind =
  'depart' | 'straight' | 'slight_left' | 'left' | 'slight_right' | 'right' | 'uturn' | 'arrive'

/** One manoeuvre of a road route (contracts/api.md, Route). */
export interface RouteStep {
  kind: StepKind
  road: { ref?: string | null; name?: string | null; fclass?: string }
  /** length of road driven after this manoeuvre */
  distance_m: number
  /** [lon, lat] where the manoeuvre happens */
  location: [number, number]
}

/** Drive to the access point on OSM roads, then walk to the node. */
export interface NavRoute {
  incident_id: number
  origin: LonLat & { source: 'gps' | 'station' }
  target: LonLat & { node_id: number }
  drive: {
    geometry: [number, number][]
    distance_m: number
    duration_s: number
    steps: RouteStep[]
  }
  walk: { geometry: [number, number][]; distance_m: number }
}

/** Recent sensor history (contracts/api.md, History). */
export interface HistoryPoint {
  /** server receive time, ISO UTC */
  ts: string
  state: NodeState
  temp_c: number
  rh_pct: number
  gas_ratio: number
  fire_prob: number
  battery_v: number
}

export interface History {
  since: string
  now: string
  /** a gap longer than this (s) after a reading in that state means the sensor went silent */
  silent_after_s: Partial<Record<NodeState, number>>
  nodes: { node_id: number; points: HistoryPoint[] }[]
}

// --- population alerts (ADR 0003) ---------------------------------------------------------

export type RiskLevel = 'high' | 'medium' | 'low'

/** A populated place to warn by Cell Broadcast (built offline by zones/). */
export interface AlertZoneProps {
  id: number
  /** Arabic OSM place name; null for a douar */
  name: string | null
  /** nearest named place, for "douar near X" */
  near: string | null
  /** WorldPop 2020 estimate, rounded to 10 */
  population: number
  risk_level: RiskLevel
  risk_percentile: number | null
  building_count: number
  tower_ids: string[]
}

export interface AlertZone {
  type: 'Feature'
  geometry: { type: 'MultiPolygon'; coordinates: number[][][][] }
  properties: AlertZoneProps
}

/** A cell tower from OpenCelliD (crowdsourced, approximate position and range). */
export interface CellTower {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: { id: string; radio: string; net: number; range_m: number; samples: number }
}

export interface FeatureCollection<F> {
  type: 'FeatureCollection'
  features: F[]
}

export interface ProposedZone {
  id: number
  /** the Arabic name used in the message */
  label: string
  population: number
  risk_level: RiskLevel
  distance_km: number
  tower_ids: string[]
}

/** Who a public alert would reach, and its Arabic text. Never sent by itself. */
export interface AlertProposal {
  incident_id: number
  radius_km: number
  zones: ProposedZone[]
  people: number
  tower_ids: string[]
  headline: string
  description: string
  instruction: string
}

/** A public alert as residents received it. */
export interface PublicAlert {
  id: number
  incident_id: number
  created_at: string
  zones: { id: number; label: string }[]
  people: number
  headline: string
  message_ar: string
  /** CAP status: "Exercise" while delivery is simulated */
  status: 'Exercise' | 'Actual'
  delivery: string
  active: boolean
}

// --- fire spread forecast (ADR 0004) ------------------------------------------------------

export interface WindReading {
  from_deg: number
  speed_ms: number
  source: string
  observed_at: string
}

export interface ForecastArea {
  type: 'Feature'
  geometry: { type: 'Polygon' | 'MultiPolygon'; coordinates: number[][][] | number[][][][] }
  /** areas burned by then with at least this probability */
  properties: { p: 0.2 | 0.5 | 0.8; horizon_min: number }
}

export interface Forecast {
  incident_id: number
  computed_at: string
  /** fire minutes since the first detection */
  fire_minutes: number
  /** fire minutes per real minute (60 in the demo) */
  time_scale: number
  advisory: true
  closed: boolean
  ignition: { lon: number; lat: number; uncertainty_m: number; at: string }
  head: { bearing_deg: number | null; speed_m_min: number }
  wind: {
    estimated_from_deg: number
    estimated_speed_ms: number
    observed_from_deg: number
    observed_speed_ms: number
    source: string
  }
  wind_reading: WindReading
  confidence: { members: number; ess_ratio: number }
  area_ha: Record<string, number>
  horizons: Record<string, { type: 'FeatureCollection'; features: ForecastArea[] }>
  observed: { node_id: number; event: 'FIRE' | 'LOST'; at: string }[]
  next_nodes: {
    node_id: number
    p_within_60: number
    p_within_120: number
    eta_min: number | null
  }[]
  threatened_zones: {
    id: number
    name: string | null
    near: string | null
    population: number
    risk_level: RiskLevel
    horizon_min: number
    p: number
  }[]
}

export interface EmberApi {
  listNodes(): Promise<SensorNode[]>
  listGateways(): Promise<Gateway[]>
  listIncidents(): Promise<Incident[]>
  riskOverlay(): Promise<RiskOverlay>
  /** recent readings; only `nodeIds` when given */
  history(minutes: number, nodeIds?: number[]): Promise<History>
  listStations(): Promise<Station[]>
  listCrews(): Promise<Crew[]>
  acknowledge(incidentId: number): Promise<Incident>
  assign(incidentId: number, crewId: number): Promise<Incident>
  setStatus(incidentId: number, status: IncidentStatus, crewId: number): Promise<Incident>
  /** road route for a crew: from `from` (live GPS) or else from the crew's station */
  route(incidentId: number, opts: { from?: LonLat; crewId?: number }): Promise<NavRoute>
  /** fire spread forecast of an incident (advisory) */
  forecast(incidentId: number): Promise<Forecast>
  listZones(): Promise<FeatureCollection<AlertZone>>
  listTowers(): Promise<FeatureCollection<CellTower>>
  alertProposal(incidentId: number): Promise<AlertProposal>
  /** broadcast the public alert; the dispatcher's confirmation is required */
  sendAlert(incidentId: number, confirmedBy: string): Promise<{ id: number; created_at: string }>
  listAlerts(activeOnly: boolean): Promise<PublicAlert[]>
  subscribe(listener: (event: LiveEvent) => void): () => void
  /** live-connection state: true when the backend's event stream is up */
  onConnection(listener: (up: boolean) => void): () => void
}
