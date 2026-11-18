// Shared test fixtures for station components.
import type { Incident, SensorNode } from '../api/types'

export const T0 = Date.parse('2026-10-01T12:00:00Z')

export const fire = (id: number, node: number, status: Incident['status']): Incident => ({
  id,
  status,
  first_node_id: node,
  estimated_origin: null,
  created_at: '2026-10-01T12:00:00Z',
  acknowledged_at: null,
  access_point: null,
  node_ids: [node],
  assigned_crew: null,
  events: [],
})

export const sensor = (id: number, extra: Partial<SensorNode> = {}): SensorNode => ({
  id,
  state: 'NORMAL',
  lon: 8.6,
  lat: 36.7,
  last_seen: '2026-10-01T12:00:39Z',
  battery_v: 4.0,
  risk_percentile: 99,
  gateway_id: 30 + id,
  link: { received: 99, lost: 1, rejected: 0 },
  ...extra,
})
