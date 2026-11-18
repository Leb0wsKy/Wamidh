import type { Incident, IncidentStatus } from '../api/types'

// Crew-side steps of the lifecycle (CLAUDE.md section 8). The station handles NEW ->
// STATION_NOTIFIED -> ACKNOWLEDGED; crews move it forward one step at a time.
const CREW_NEXT: Partial<Record<IncidentStatus, IncidentStatus[]>> = {
  ACKNOWLEDGED: ['EN_ROUTE', 'FALSE_ALARM'],
  EN_ROUTE: ['ON_SITE', 'FALSE_ALARM'],
  ON_SITE: ['UNDER_CONTROL', 'FALSE_ALARM'],
  UNDER_CONTROL: ['CLOSED'],
}

export function crewActions(status: IncidentStatus): IncidentStatus[] {
  return CREW_NEXT[status] ?? []
}

/**
 * What the crew's incident card offers. Before arrival: Go (which also marks the crew en route)
 * and False alarm, checked before setting off. Arrival (On site) is recorded at the end of the
 * navigation, so the card never asks for it; once on site, only Under control, then Closed.
 */
export function crewCard(status: IncidentStatus): { go: boolean; actions: IncidentStatus[] } {
  switch (status) {
    case 'ACKNOWLEDGED':
    case 'EN_ROUTE':
      return { go: true, actions: ['FALSE_ALARM'] }
    case 'ON_SITE':
      return { go: false, actions: ['UNDER_CONTROL'] }
    case 'UNDER_CONTROL':
      return { go: false, actions: ['CLOSED'] }
    default:
      return { go: false, actions: [] }
  }
}

export function isOpen(status: IncidentStatus): boolean {
  return status !== 'CLOSED' && status !== 'FALSE_ALARM'
}

export interface CrewBoard {
  mine: Incident[]
  available: Incident[]
  takenByOthers: Incident[]
  awaitingStation: Incident[]
}

/** Every live fire as a given crew sees it. */
export function crewBoard(incidents: Incident[], crewId: number | null): CrewBoard {
  const board: CrewBoard = { mine: [], available: [], takenByOthers: [], awaitingStation: [] }
  for (const inc of incidents) {
    if (!isOpen(inc.status)) continue
    if (inc.status === 'NEW' || inc.status === 'STATION_NOTIFIED') board.awaitingStation.push(inc)
    else if (inc.assigned_crew == null) board.available.push(inc)
    else if (inc.assigned_crew === crewId) board.mine.push(inc)
    else board.takenByOthers.push(inc)
  }
  return board
}

export interface Spread {
  incidentId: number
  nodeId: number
}

/**
 * Fire-spread events (a further sensor detecting the same, still-burning fire) not reported
 * yet. `seen` is updated, so each spread is announced once.
 */
export function newSpreads(seen: Set<string>, incidents: Incident[]): Spread[] {
  const fresh: Spread[] = []
  for (const inc of incidents) {
    inc.events.forEach((e, i) => {
      const key = `${inc.id}:${i}`
      if (e.type !== 'fire_spread' || seen.has(key)) return
      seen.add(key)
      fresh.push({ incidentId: inc.id, nodeId: Number(e.payload.node_id) })
    })
  }
  return fresh
}

/** Apply a live incident update to the open-incident list: newest first, closed ones dropped. */
export function mergeIncident(list: Incident[], update: Incident): Incident[] {
  const rest = list.filter((i) => i.id !== update.id)
  const next = isOpen(update.status) ? [...rest, update] : rest
  return next.sort((a, b) => b.id - a.id)
}

/**
 * The crew's mission shown in full (the others fold to one line): the one they tapped,
 * else the newest fire still burning, else the newest. `mine` is newest first.
 */
export function activeMission(mine: Incident[], chosenId: number | null): Incident | null {
  return (
    mine.find((i) => i.id === chosenId) ??
    mine.find((i) => i.status !== 'UNDER_CONTROL') ??
    mine[0] ??
    null
  )
}

export const awaitingStation = (i: Incident): boolean =>
  i.status === 'NEW' || i.status === 'STATION_NOTIFIED'

/** Dispatcher's incident list: fires still burning, then under control, then closed (the
 *  history, with false alarms), each group newest first. */
export function dispatchOrder(incidents: Incident[]): Incident[] {
  const newest = (a: Incident, b: Incident) => b.id - a.id
  const rank = (i: Incident) => (!isOpen(i.status) ? 2 : i.status === 'UNDER_CONTROL' ? 1 : 0)
  return [...incidents].sort((a, b) => rank(a) - rank(b) || newest(a, b))
}

/** Apply a live incident update to the full history: replaced by id, closed ones kept. */
export function upsertIncident(list: Incident[], update: Incident): Incident[] {
  return [...list.filter((i) => i.id !== update.id), update].sort((a, b) => b.id - a.id)
}

/** The Incidents tab badge: fires still burning, urgent while one waits for the station. */
export function incidentBadge(incidents: Incident[]): { count: number; urgent: boolean } {
  const burning = incidents.filter((i) => i.status !== 'UNDER_CONTROL')
  return { count: burning.length, urgent: burning.some(awaitingStation) }
}

/** When the fire ended (ms): brought under control, else closed or found to be a false alarm.
 *  Null while it still burns. */
export function endedAt(incident: Incident): number | null {
  if (incident.status !== 'UNDER_CONTROL' && isOpen(incident.status)) return null
  const at = (status: string) =>
    incident.events.find((ev) => ev.type === 'status' && ev.payload.status === status)
  const e = at('UNDER_CONTROL') ?? at('CLOSED') ?? at('FALSE_ALARM')
  return e ? Date.parse(e.ts) : null
}
