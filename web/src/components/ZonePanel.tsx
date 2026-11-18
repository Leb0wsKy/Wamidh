import { useTranslation } from 'react-i18next'
import type { AlertZoneProps, CellTower, PublicAlert } from '../api/types'
import { formatCount } from '../domain/time'
import { zoneLabel } from '../domain/zones'
import { Icon } from './Icon'
import { PhoneAlertCard } from './PhoneAlertCard'

export const RISK_TONE: Record<AlertZoneProps['risk_level'], string> = {
  high: 'bg-ember text-white',
  medium: 'bg-alert-fill text-ink',
  low: 'bg-ink/[0.08] text-ink',
}

interface Props {
  zone: AlertZoneProps
  /** the towers serving this zone */
  towers: CellTower[]
  /** the alert in progress for this zone, if any */
  alert: PublicAlert | undefined
  onClose: () => void
}

/** One alert zone: who lives there, the fire risk around it, and how they would be warned. */
export function ZonePanel({ zone, towers, alert, onClose }: Props) {
  const { t, i18n } = useTranslation()

  return (
    <div className="flex flex-col gap-4 px-4 pb-4">
      <div className="flex items-start gap-2">
        <h3 className="text-xl font-semibold text-ink">{zoneLabel(zone, t)}</h3>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('residents.close')}
          className="ms-auto -me-1 grid size-9 place-items-center rounded-md text-ink-2 hover:bg-paper hover:text-ink"
        >
          <Icon name="close" size={18} />
        </button>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <div>
          <dt className="eg-label">{t('residents.population')}</dt>
          <dd className="mt-1 text-2xl font-semibold tabular-nums">
            {formatCount(zone.population, i18n.language)}
          </dd>
        </div>
        <div>
          <dt className="eg-label">{t('residents.risk')}</dt>
          <dd className="mt-1 flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 text-sm leading-6 font-semibold ${RISK_TONE[zone.risk_level]}`}
            >
              {t(`residents.riskLevel.${zone.risk_level}`)}
            </span>
            {zone.risk_percentile !== null && (
              <span className="text-sm text-ink-2 tabular-nums">
                {t('residents.percentile', { p: Math.round(zone.risk_percentile) })}
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="eg-label">{t('residents.buildings')}</dt>
          <dd className="mt-1 text-lg font-medium tabular-nums">
            {formatCount(zone.building_count, i18n.language)}
          </dd>
        </div>
      </dl>

      <section>
        <h4 className="eg-label mb-1.5">{t('residents.servingTowers')}</h4>
        {towers.length === 0 ? (
          <p className="text-ink-2">{t('residents.noTowers')}</p>
        ) : (
          <ul className="space-y-1">
            {towers.map((tw) => (
              <li key={tw.properties.id} className="flex items-center gap-2 text-sm">
                <Icon name="broadcast" size={16} className="text-ink-2" />
                <span dir="ltr" className="tabular-nums">
                  {tw.properties.radio} · {tw.properties.id}
                </span>
                <span dir="ltr" className="ms-auto text-ink-2 tabular-nums">
                  ~{(tw.properties.range_m / 1000).toFixed(1)} km
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h4 className="eg-label mb-1.5">{t('residents.activeAlert')}</h4>
        {alert ? (
          <PhoneAlertCard alert={alert} />
        ) : (
          <p className="text-ink-2">{t('residents.noActiveAlert')}</p>
        )}
      </section>
    </div>
  )
}
