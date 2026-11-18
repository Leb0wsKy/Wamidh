import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  useAssign,
  useCrewName,
  useCrews,
  useNodes,
  useOpenIncidents,
  useSetStatus,
} from '../api/queries'
import { CrewFireSummary } from '../components/CrewFireSummary'
import { CrewIncidentCard } from '../components/CrewIncidentCard'
import { Icon } from '../components/Icon'
import { activeMission, crewActions, crewBoard } from '../domain/incident'
import { useMyCrew, usePosition } from './crewDevice'

export function CrewPage() {
  const { t } = useTranslation()
  const crews = useCrews().data ?? []
  const crewName = useCrewName()
  const incidents = useOpenIncidents().data ?? []
  const sensorCount = useNodes().data?.length ?? 0
  const setStatus = useSetStatus()
  const assign = useAssign()
  const position = usePosition()
  const [myCrew, setMyCrew] = useMyCrew()
  const navigate = useNavigate()

  const board = crewBoard(incidents, myCrew)
  const [chosenId, setChosenId] = useState<number | null>(null)
  const active = activeMission(board.mine, chosenId)
  const others = [...board.available, ...board.awaitingStation, ...board.takenByOthers]

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-md flex-col gap-6 p-4">
        {/* Big touch targets: chosen once per shift, often with gloves on. */}
        <fieldset>
          <legend className="eg-label mb-2">{t('crew.chooseCrew')}</legend>
          <div className="grid auto-cols-fr grid-flow-col gap-px overflow-hidden rounded-lg border border-line-strong bg-line-strong">
            {crews.map((c) => {
              const mine = c.id === myCrew
              return (
                <button
                  key={c.id}
                  type="button"
                  aria-pressed={mine}
                  onClick={() => setMyCrew(mine ? null : c.id)}
                  className={`min-h-14 px-2 text-base font-semibold ${
                    mine ? 'bg-ink text-white' : 'bg-surface text-ink active:bg-paper'
                  }`}
                >
                  {c.name}
                </button>
              )
            })}
          </div>
        </fieldset>

        {myCrew !== null && active && (
          <section className="flex flex-col gap-2">
            <h2 className="eg-label">{t('crew.myMissions')}</h2>
            <CrewIncidentCard
              incident={active}
              position={position}
              onStatus={(id, status) => setStatus.mutate({ id, status, crewId: myCrew })}
              onGo={(id) => {
                // Pressing Go is leaving the station: the dispatcher sees the crew en route.
                if (crewActions(active.status).includes('EN_ROUTE')) {
                  setStatus.mutate({ id, status: 'EN_ROUTE', crewId: myCrew })
                }
                navigate(`/crew/navigate/${id}`)
              }}
            />
            {/* Other missions of this crew fold to one line; tap to open. */}
            {board.mine
              .filter((i) => i.id !== active.id)
              .map((i) => {
                const settled = i.status === 'UNDER_CONTROL'
                return (
                  <button
                    key={i.id}
                    type="button"
                    onClick={() => setChosenId(i.id)}
                    className="flex min-h-12 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-start text-sm"
                  >
                    <Icon
                      name={settled ? 'check' : 'flame'}
                      size={18}
                      filled={!settled}
                      className={settled ? 'text-ok' : 'text-ember'}
                    />
                    <span className="font-semibold text-ink">
                      {t('station.node')} {i.first_node_id}
                    </span>
                    <span dir="ltr" className="text-ink-2">
                      #{i.id}
                    </span>
                    <span className="ms-auto text-ink-2">{t(`incidentStatus.${i.status}`)}</span>
                    <Icon name="chevron" size={16} className="text-ink-3" />
                  </button>
                )
              })}
          </section>
        )}

        <section className="flex flex-col gap-3">
          {(others.length > 0 || board.mine.length === 0) && (
            <h2 className="eg-label">{t('crew.liveFires')}</h2>
          )}
          {others.length === 0 && board.mine.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-line bg-surface px-4 py-10 text-center">
              <span className="grid size-12 place-items-center rounded-full bg-ok-soft text-ok">
                <Icon name="check" size={26} strokeWidth={2.25} />
              </span>
              <p className="text-lg font-semibold text-ink">{t('crew.noFires')}</p>
              <p className="flex items-center gap-2 text-sm text-ink-2">
                <Icon name="sensor" size={16} />
                {t('station.watching', { n: sensorCount })}
              </p>
            </div>
          )}
          {others.map((inc) => (
            <CrewFireSummary
              key={inc.id}
              incident={inc}
              crewName={crewName}
              onTake={(id) => (myCrew === null ? undefined : assign.mutate({ id, crewId: myCrew }))}
            />
          ))}
          {myCrew === null && others.length > 0 && (
            <p className="text-center font-medium text-alert">{t('crew.selectCrew')}</p>
          )}
        </section>
      </div>
    </div>
  )
}
