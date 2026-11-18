import type { Incident, SensorNode } from '../api/types'

export interface Situation {
  /** overall state, for the headline colour */
  level: 'normal' | 'alert' | 'fire'
  online: number
  total: number
  alerts: number
  fires: number
  /** gateways relaying at least one sensor still online */
  gateways: number
  /** packets lost over all sensor links, % */
  lossPct: number
  batteryMin: number | null
  batteryAvg: number | null
  /** most recent contact from any sensor (ISO) */
  lastReport: string | null
}

const SILENT: SensorNode['state'][] = ['OFFLINE', 'LOST_PROBABLY_BURNED']

/** The station's one-glance summary, computed only from what sensors and backend report. */
export function situation(nodes: SensorNode[], incidents: Incident[]): Situation {
  const online = nodes.filter((n) => !SILENT.includes(n.state))
  const fires = nodes.filter((n) => n.state === 'FIRE').length
  const alerts = nodes.filter((n) => n.state === 'ALERT').length
  const burning = incidents.some((i) => i.status !== 'UNDER_CONTROL')

  const received = nodes.reduce((a, n) => a + (n.link?.received ?? 0), 0)
  const lost = nodes.reduce((a, n) => a + (n.link?.lost ?? 0), 0)
  const volts = nodes.map((n) => n.battery_v).filter((v): v is number => v !== null)
  const seen = nodes.map((n) => n.last_seen).filter((s): s is string => s !== null)

  return {
    level: fires > 0 || burning ? 'fire' : alerts > 0 ? 'alert' : 'normal',
    online: online.length,
    total: nodes.length,
    alerts,
    fires,
    gateways: new Set(online.map((n) => n.gateway_id).filter((g) => g !== null)).size,
    lossPct: received + lost > 0 ? (lost / (received + lost)) * 100 : 0,
    batteryMin: volts.length ? Math.min(...volts) : null,
    batteryAvg: volts.length ? volts.reduce((a, v) => a + v, 0) / volts.length : null,
    lastReport: seen.length ? seen.reduce((a, b) => (Date.parse(b) > Date.parse(a) ? b : a)) : null,
  }
}
