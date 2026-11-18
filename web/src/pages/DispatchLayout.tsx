// Shared by the dispatcher's tabs (Caserne, Incidents): the siren and the alarm band live
// here, so switching tabs never silences an unacknowledged fire.

import { useEffect, useMemo, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useAcknowledge, useOpenIncidents } from '../api/queries'
import { AlarmBand } from '../components/AlarmBand'
import { useAlarm } from '../components/useAlarm'
import { awaitingStation, dispatchOrder, newSpreads, type Spread } from '../domain/incident'
import { useNow } from '../domain/status'
import type { DispatchContext } from './dispatchContext'

export function DispatchLayout() {
  const incidentsQuery = useOpenIncidents()
  const incidents = useMemo(() => dispatchOrder(incidentsQuery.data ?? []), [incidentsQuery.data])
  const ack = useAcknowledge()
  const now = useNow()

  // The alarm rings by itself while any fire incident waits for acknowledgement.
  const ringing = incidents.some(awaitingStation)
  const { soundLocked, chime } = useAlarm(ringing)

  // A fire spreading to a further sensor: notice for 30 s and a chime, even if acknowledged.
  // Spreads that happened before the page was opened are remembered, not announced.
  const seenSpreads = useRef<Set<string> | null>(null)
  const [spread, setSpread] = useState<Spread | null>(null)
  const incidentsLoaded = incidentsQuery.isSuccess
  useEffect(() => {
    if (!incidentsLoaded) return
    if (seenSpreads.current === null) {
      seenSpreads.current = new Set()
      newSpreads(seenSpreads.current, incidents)
      return
    }
    const fresh = newSpreads(seenSpreads.current, incidents)
    const latest = fresh.at(-1)
    if (!latest) return
    setSpread(latest)
    chime()
    const id = setTimeout(() => setSpread(null), 30_000)
    return () => clearTimeout(id)
  }, [incidents, incidentsLoaded, chime])

  const context: DispatchContext = { soundLocked, spread }
  return (
    <div className="flex h-full flex-col">
      <AlarmBand incidents={incidents} now={now} onAcknowledge={(id) => ack.mutate(id)} />
      <div className="min-h-0 flex-1">
        <Outlet context={context} />
      </div>
    </div>
  )
}
