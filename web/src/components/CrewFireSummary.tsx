import { useTranslation } from 'react-i18next'
import type { Incident } from '../api/types'
import { formatElapsed, useNow } from '../domain/status'
import { Icon } from './Icon'

interface Props {
  incident: Incident
  crewName: (crewId: number) => string
  onTake: (incidentId: number) => void
}

/** One live fire in the crew list: take it, see who has it, or wait for the station. */
export function CrewFireSummary({ incident, crewName, onTake }: Props) {
  const { t } = useTranslation()
  const now = useNow()
  const awaiting = incident.status === 'NEW' || incident.status === 'STATION_NOTIFIED'
  const taken = incident.assigned_crew != null
  const open = !awaiting && !taken

  return (
    <article
      className={`rounded-e-lg border border-s-4 border-line bg-surface p-4 ${
        open ? 'border-s-ember' : 'border-s-line-strong'
      }`}
    >
      <header className="flex items-center gap-2">
        <Icon name="flame" size={20} filled={open} className={open ? 'text-ember' : 'text-ink-3'} />
        <h3 className="text-lg font-semibold text-ink">
          {t('station.node')} {incident.node_ids.join(', ')}
          <span dir="ltr" className="ms-2 text-sm font-medium text-ink-2">
            #{incident.id}
          </span>
        </h3>
        <span className="ms-auto text-sm text-ink-2 tabular-nums">
          {formatElapsed(now - Date.parse(incident.created_at))}
        </span>
      </header>
      <p className="mt-1 text-sm text-ink-2">{t(`incidentStatus.${incident.status}`)}</p>

      {awaiting && <p className="mt-3 font-medium text-alert">{t('crew.awaitingStation')}</p>}
      {!awaiting && taken && (
        <p className="mt-3 flex items-center gap-2 font-medium text-ink">
          <Icon name="truck" size={18} className="text-ink-2" />
          {t('crew.takenBy', { crew: crewName(incident.assigned_crew as number) })}
        </p>
      )}
      {open && (
        <button
          type="button"
          onClick={() => onTake(incident.id)}
          className="mt-3 min-h-14 w-full rounded-lg bg-ember text-lg font-bold text-white active:bg-ember-deep"
        >
          {t('crew.take')}
        </button>
      )}
    </article>
  )
}
