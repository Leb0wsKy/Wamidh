// Which sensors the station's list shows, out of the whole installation (200 in the pilot).

import type { SensorNode } from '../api/types'
import { bySeverity } from './nodeState'

const byRisk = (a: SensorNode, b: SensorNode): number =>
  (b.risk_percentile ?? -1) - (a.risk_percentile ?? -1) || a.id - b.id

const bySeverityThenRisk = (a: SensorNode, b: SensorNode): number =>
  bySeverity(a.state, b.state) || byRisk(a, b)

/**
 * The rows of the sensor list, in order, and how many sensors match.
 * - No search: every sensor in alarm (fire, lost, alert, offline) first, never cut off, then
 *   the highest-risk calm sensors until `limit` rows.
 * - Search by number: the exact sensor first, then the numbers starting with the query.
 */
export function ledgerRows(
  nodes: SensorNode[],
  query: string,
  limit: number,
): { rows: SensorNode[]; total: number } {
  const q = query.trim().replace(/^#/, '')
  if (q === '') {
    const alarmed = nodes.filter((n) => n.state !== 'NORMAL').sort(bySeverityThenRisk)
    const calm = nodes.filter((n) => n.state === 'NORMAL').sort(byRisk)
    return {
      rows: [...alarmed, ...calm.slice(0, Math.max(0, limit - alarmed.length))],
      total: nodes.length,
    }
  }
  const matches = nodes
    .filter((n) => String(n.id).startsWith(q))
    .sort((a, b) => Number(b.id === Number(q)) - Number(a.id === Number(q)) || a.id - b.id)
  return { rows: matches.slice(0, limit), total: matches.length }
}
