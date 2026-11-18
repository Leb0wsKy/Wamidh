import type { Incident, SensorNode } from '../api/types'
import { WATCH } from '../config'

export type WatchKind = 'lost' | 'silent' | 'battery' | 'radio'

export interface WatchItem {
  nodeId: number
  kind: WatchKind
  /** volts for 'battery', % lost for 'radio' */
  value?: number
  /** last contact, for 'silent' */
  since?: string | null
}

const ORDER: Record<WatchKind, number> = { lost: 0, silent: 1, battery: 2, radio: 3 }

/** Maintenance worth a look, most serious first: lost or silent sensors, low batteries,
 *  lossy radio links. Empty when every sensor is healthy. */
export function watchItems(nodes: SensorNode[]): WatchItem[] {
  const items: WatchItem[] = []
  for (const n of nodes) {
    if (n.state === 'LOST_PROBABLY_BURNED') items.push({ nodeId: n.id, kind: 'lost' })
    else if (n.state === 'OFFLINE') items.push({ nodeId: n.id, kind: 'silent', since: n.last_seen })
    if (n.battery_v !== null && n.battery_v <= WATCH.lowBatteryV)
      items.push({ nodeId: n.id, kind: 'battery', value: n.battery_v })
    const sent = n.link ? n.link.received + n.link.lost : 0
    if (n.link && sent > 0) {
      const pct = (n.link.lost / sent) * 100
      if (pct > WATCH.packetLossPct) items.push({ nodeId: n.id, kind: 'radio', value: pct })
    }
  }
  return items.sort((a, b) => ORDER[a.kind] - ORDER[b.kind] || a.nodeId - b.nodeId)
}

export interface Activity {
  fires: number
  falseAlarms: number
  alertedSensors: number
  lastFire: { nodeId: number; at: string } | null
}

const DAY_MS = 24 * 3600 * 1000

/** What happened in the last 24 h, from the incident history and each sensor's last alert. */
export function activity24h(incidents: Incident[], nodes: SensorNode[], now: number): Activity {
  const recent = incidents.filter((i) => now - Date.parse(i.created_at) <= DAY_MS)
  const fires = recent.filter((i) => i.status !== 'FALSE_ALARM')
  const latest = [...fires].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0]
  return {
    fires: fires.length,
    falseAlarms: recent.filter((i) => i.status === 'FALSE_ALARM').length,
    alertedSensors: nodes.filter(
      (n) => n.last_alert_at && now - Date.parse(n.last_alert_at) <= DAY_MS,
    ).length,
    lastFire: latest ? { nodeId: latest.first_node_id, at: latest.created_at } : null,
  }
}

export interface RecentEvent {
  incident: Incident
  event: Incident['events'][number]
}

/** The latest audit-log entries of every incident, newest first (the station's journal). */
export function recentEvents(incidents: Incident[], limit: number): RecentEvent[] {
  return incidents
    .flatMap((incident) => incident.events.map((event) => ({ incident, event })))
    .sort(
      (a, b) => Date.parse(b.event.ts) - Date.parse(a.event.ts) || b.incident.id - a.incident.id,
    )
    .slice(0, limit)
}
