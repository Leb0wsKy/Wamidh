import { useTranslation } from 'react-i18next'
import type { Incident } from '../api/types'
import { awaitingStation } from '../domain/incident'
import { formatElapsed } from '../domain/status'
import { Icon } from './Icon'

interface Props {
  /** open incidents, in dispatch order */
  incidents: Incident[]
  now: number
  onAcknowledge: (incidentId: number) => void
}

/** The ember band across the top while a fire waits for the station: the first thing seen. */
export function AlarmBand({ incidents, now, onAcknowledge }: Props) {
  const { t } = useTranslation()
  const waiting = incidents.filter(awaitingStation)
  const first = waiting[0]
  if (!first) return null

  return (
    <div
      role="alert"
      className="eg-flash flex min-h-14 shrink-0 items-center gap-4 px-5 py-2 text-white"
    >
      <Icon name="flame" size={26} filled />
      <p className="text-2xl font-bold">{t('station.fireAt', { node: first.first_node_id })}</p>
      <p className="text-2xl font-medium tabular-nums opacity-90">
        {formatElapsed(now - Date.parse(first.created_at))}
      </p>
      {waiting.length > 1 && (
        <p className="rounded-full border border-white/50 px-3 py-0.5 text-sm font-semibold">
          {t('station.othersWaiting', { n: waiting.length - 1 })}
        </p>
      )}
      <button
        type="button"
        onClick={() => onAcknowledge(first.id)}
        className="ms-auto min-h-11 rounded-md bg-white px-6 text-lg font-bold text-ember hover:bg-ember-soft focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-white"
      >
        {t('station.acknowledge')}
      </button>
    </div>
  )
}
