import type { IncidentEvent } from '../api/types'

type T = (key: string, opts?: Record<string, unknown>) => string

/** One audit-log entry as a sentence. */
export function eventText(e: IncidentEvent, t: T, crewName: (crewId: number) => string): string {
  if (e.type === 'crew_assigned')
    return t('events.crew_assigned', { crew: crewName(Number(e.payload.crew_id)) })
  if (['node_fire', 'fire_spread', 'node_lost'].includes(e.type))
    return t(`events.${e.type}`, { node: e.payload.node_id })
  if (e.type === 'public_alert') return t('events.public_alert', { people: e.payload.people })
  if (e.type === 'status')
    return t('events.status', { status: t(`incidentStatus.${String(e.payload.status)}`) })
  return t(`events.${e.type}`, { defaultValue: e.type })
}
