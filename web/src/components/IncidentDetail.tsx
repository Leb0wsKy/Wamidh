import { useTranslation } from 'react-i18next'
import type { Incident } from '../api/types'
import { eventText } from '../domain/events'
import { awaitingStation, endedAt, isOpen } from '../domain/incident'
import { formatElapsed } from '../domain/status'
import { formatTime } from '../domain/time'
import { Icon } from './Icon'

interface Props {
  incident: Incident
  now: number
  onAcknowledge: (incidentId: number) => void
  /** crew id -> name, to show who took the incident */
  crewName?: (crewId: number) => string
}

/** One incident in full: what burns, since when, who goes, and the complete audit log. */
export function IncidentDetail({
  incident,
  now,
  onAcknowledge,
  crewName = (id) => `#${id}`,
}: Props) {
  const { t, i18n } = useTranslation()
  const needsAck = awaitingStation(incident)
  const settled = incident.status === 'UNDER_CONTROL' || !isOpen(incident.status)
  const falseAlarm = incident.status === 'FALSE_ALARM'

  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-wrap items-center gap-3">
        <Icon
          name={falseAlarm ? 'close' : settled ? 'check' : 'flame'}
          size={28}
          filled={!settled}
          className={falseAlarm ? 'text-ink-2' : settled ? 'text-ok' : 'text-ember'}
        />
        <h2 className="text-2xl font-semibold text-ink">
          {t('station.node')} {incident.first_node_id}
        </h2>
        <span dir="ltr" className="text-ink-2">
          #{incident.id}
        </span>
        <span
          className={`ms-auto rounded-full px-3 py-1 text-sm font-semibold ${
            needsAck ? 'bg-ember text-white' : 'bg-ink/[0.06] text-ink'
          }`}
        >
          {t(`incidentStatus.${incident.status}`)}
        </span>
      </header>

      {needsAck && (
        <button
          type="button"
          onClick={() => onAcknowledge(incident.id)}
          className="min-h-12 rounded-md bg-ember text-lg font-bold text-white hover:bg-ember-deep focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          {t('station.acknowledge')}
        </button>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-y border-line py-4 sm:grid-cols-3">
        <div>
          <dt className="eg-label">{t('incidents.detectedAt')}</dt>
          <dd className="mt-1 text-lg font-medium tabular-nums">
            {formatTime(incident.created_at, i18n.language)}
          </dd>
        </div>
        <div>
          <dt className="eg-label">{t('incidents.burning')}</dt>
          <dd className="mt-1 text-lg font-medium tabular-nums">
            {formatElapsed((endedAt(incident) ?? now) - Date.parse(incident.created_at))}
          </dd>
        </div>
        <div>
          <dt className="eg-label">{t('incidents.sensors')}</dt>
          <dd className="mt-1 text-lg font-medium tabular-nums">{incident.node_ids.join(', ')}</dd>
        </div>
        <div>
          <dt className="eg-label">{t('incidents.crew')}</dt>
          <dd className="mt-1 flex items-center gap-2 text-lg font-medium">
            {incident.assigned_crew != null ? (
              <>
                <Icon name="truck" size={18} className="text-ink-2" />
                {crewName(incident.assigned_crew)}
              </>
            ) : (
              <span className="text-ink-2">{t('incidents.unassigned')}</span>
            )}
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="eg-label">{t('crew.accessPoint')}</dt>
          <dd className="mt-1 text-lg font-medium">
            {incident.access_point
              ? t(`roadType.${incident.access_point.road_type}`, {
                  defaultValue: incident.access_point.road_type,
                })
              : '—'}
          </dd>
        </div>
      </dl>

      <section>
        <h3 className="eg-label mb-3">{t('station.timeline')}</h3>
        <ol className="space-y-2.5 border-s border-line-strong ps-4">
          {incident.events.map((e, i) => (
            <li key={i} className="relative flex gap-4">
              <span
                aria-hidden
                className="absolute -start-[21.5px] top-[7px] size-2.5 rounded-full border-2 border-surface bg-ink-3"
              />
              <time className="shrink-0 text-ink-2 tabular-nums" dateTime={e.ts}>
                {formatTime(e.ts, i18n.language)}
              </time>
              <span className="text-ink">{eventText(e, t, crewName)}</span>
            </li>
          ))}
        </ol>
      </section>
    </article>
  )
}
