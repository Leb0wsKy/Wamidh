import { useTranslation } from 'react-i18next'
import type { Incident, IncidentStatus, LonLat } from '../api/types'
import { crewCard } from '../domain/incident'
import { distanceKm } from '../domain/navigation'
import { formatElapsed, useNow } from '../domain/status'
import { Icon } from './Icon'

interface Props {
  incident: Incident
  /** the phone's position, when the browser shares it */
  position: LonLat | null
  onStatus: (incidentId: number, status: IncidentStatus) => void
  /** start in-app navigation to this incident */
  onGo: (incidentId: number) => void
}

export function CrewIncidentCard({ incident, position, onStatus, onGo }: Props) {
  const { t } = useTranslation()
  const now = useNow()
  // Drive to the access point; if unknown, towards the estimated fire zone.
  const target = incident.access_point ?? incident.estimated_origin
  const { go, actions } = crewCard(incident.status)

  return (
    <article className="rounded-e-lg border border-s-4 border-line border-s-ember bg-surface shadow-sm">
      <header className="flex items-center gap-2 px-4 pt-3">
        <Icon name="flame" size={20} filled className="text-ember" />
        <h2 className="text-lg font-bold text-ink">
          {t('station.node')} {incident.first_node_id}
          <span dir="ltr" className="ms-2 text-sm font-medium text-ink-2">
            #{incident.id}
          </span>
        </h2>
        <span className="ms-auto rounded-full bg-ember-soft px-2.5 py-0.5 text-xs font-semibold text-ember">
          {t(`incidentStatus.${incident.status}`)}
        </span>
      </header>

      <div className="flex flex-col gap-3 p-4 pt-2">
        <p className="text-sm text-ink-2 tabular-nums">
          {t('crew.detected', { t: formatElapsed(now - Date.parse(incident.created_at)) })}
        </p>
        <dl className="grid grid-cols-[auto_1fr] items-start gap-x-5">
          <div className="flex flex-col gap-0.5">
            <dt className="eg-label">{t('crew.distance')}</dt>
            <dd
              dir="ltr"
              className="text-start text-2xl leading-tight font-bold text-ink tabular-nums"
            >
              {position && target ? `${distanceKm(position, target).toFixed(1)} km` : '—'}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="eg-label">{t('crew.accessPoint')}</dt>
            <dd className="text-sm leading-snug font-medium text-ink">
              {incident.access_point
                ? t('crew.leaveVehicle', {
                    road: t(`roadType.${incident.access_point.road_type}`, {
                      defaultValue: incident.access_point.road_type,
                    }),
                  })
                : t('crew.noAccessPoint')}
            </dd>
          </div>
        </dl>

        {go && target && (
          <button
            type="button"
            onClick={() => onGo(incident.id)}
            className="flex min-h-16 items-center justify-center gap-3 rounded-lg bg-ember text-3xl font-bold text-white active:bg-ember-deep focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-ink"
          >
            <Icon name="straight" size={30} strokeWidth={2.5} />
            {t('crew.go')}
          </button>
        )}

        {actions.length > 0 && (
          <div className="flex flex-col gap-2">
            {actions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => onStatus(incident.id, s)}
                className={
                  s === 'FALSE_ALARM'
                    ? 'min-h-14 rounded-lg border border-line-strong bg-surface px-3 text-base font-semibold text-ink-2'
                    : // On site, the one step left is the main action: as large as Go was.
                      'flex min-h-16 items-center justify-center gap-3 rounded-lg bg-ink px-3 text-2xl font-bold text-white active:bg-ink-2 focus-visible:outline-4 focus-visible:outline-offset-4 focus-visible:outline-ink'
                }
              >
                {s !== 'FALSE_ALARM' && <Icon name="check" size={26} strokeWidth={2.5} />}
                {t(`incidentStatus.${s}`)}
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  )
}
