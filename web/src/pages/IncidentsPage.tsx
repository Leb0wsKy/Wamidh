import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAcknowledge, useAllIncidents, useCrewName } from '../api/queries'
import { IncidentDetail } from '../components/IncidentDetail'
import { IncidentList } from '../components/IncidentList'
import { dispatchOrder } from '../domain/incident'
import { useNow } from '../domain/status'

/** Incidents tab: the list on one side, the selected incident in full on the other. */
export function IncidentsPage() {
  const { t } = useTranslation()
  const incidents = dispatchOrder(useAllIncidents().data ?? [])
  const crewName = useCrewName()
  const ack = useAcknowledge()
  const now = useNow()
  const [chosenId, setChosenId] = useState<number | null>(null)
  // The one clicked, else the newest fire still burning (first in dispatch order).
  const selected = incidents.find((i) => i.id === chosenId) ?? incidents[0] ?? null

  if (incidents.length === 0) {
    return (
      <div className="grid h-full place-items-center p-6">
        <p className="max-w-sm text-center text-ink-2">{t('incidents.empty')}</p>
      </div>
    )
  }

  return (
    <div className="grid h-full grid-cols-1 md:grid-cols-[24rem_1fr] md:grid-rows-[minmax(0,1fr)]">
      <div className="overflow-y-auto border-line p-5 md:border-e">
        <IncidentList
          incidents={incidents}
          selectedId={selected?.id ?? null}
          onSelect={setChosenId}
          crewName={crewName}
          now={now}
        />
      </div>
      <div className="overflow-y-auto bg-surface p-6 md:p-8">
        {selected && (
          <div className="mx-auto max-w-2xl">
            <IncidentDetail
              incident={selected}
              now={now}
              crewName={crewName}
              onAcknowledge={(id) => ack.mutate(id)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
