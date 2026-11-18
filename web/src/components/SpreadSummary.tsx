import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { Forecast } from '../api/types'
import { compassPoint, confidenceLevel, etaLabel } from '../domain/spread'
import { formatClock, formatCount } from '../domain/time'
import { zoneLabel } from '../domain/zones'
import { Icon } from './Icon'

const KMH = 3.6

/** An arrow pointing along a bearing (degrees from north, clockwise). */
export function BearingArrow({ deg, size = 28 }: { deg: number; size?: number }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      width={size}
      height={size}
      style={{ transform: `rotate(${deg}deg)` }}
      className="shrink-0"
    >
      <path d="M12 2 19 20 12 16 5 20Z" fill="currentColor" />
    </svg>
  )
}

/** Where the head of the fire runs, how fast, the wind behind it and how sure the model is. */
export function SpreadSummary({ forecast: f }: { forecast: Forecast }) {
  const { t, i18n } = useTranslation()
  const toward = (deg: number) => t(`compass.to.${compassPoint(deg)}`)
  const from = (deg: number) => t(`compass.from.${compassPoint(deg)}`)
  const bearing = f.head.bearing_deg
  const conf = confidenceLevel(f.confidence.ess_ratio)
  const source = t(`spread.source.${f.wind.source.split(' ')[0]}`, { defaultValue: f.wind.source })

  return (
    <div className="flex flex-col gap-4 px-4 pb-4">
      <div className="flex items-center gap-3">
        {bearing !== null && (
          <span className="grid size-12 place-items-center rounded-full bg-ember-soft text-ember">
            <BearingArrow deg={bearing} />
          </span>
        )}
        <div>
          <h3 className="text-xl font-semibold text-ink">
            {bearing === null ? t('spread.noHead') : t('spread.heading', { dir: toward(bearing) })}
          </h3>
          <p className="text-ink-2 tabular-nums">
            <span dir="ltr" className="font-semibold text-ink">
              ~{Math.round(f.head.speed_m_min)} m/min
            </span>
          </p>
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <div>
          <dt className="eg-label">{t('spread.ignition')}</dt>
          <dd className="mt-1 font-medium tabular-nums">
            {formatClock(f.ignition.at)}{' '}
            <span dir="ltr" className="text-ink-2">
              ± {formatCount(f.ignition.uncertainty_m, i18n.language)} m
            </span>
          </dd>
        </div>
        <div>
          <dt className="eg-label">{t('spread.sinceDetection')}</dt>
          <dd className="mt-1 font-medium tabular-nums">
            <span dir="ltr">{Math.round(f.fire_minutes)} min</span>
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="eg-label">{t('spread.wind')}</dt>
          <dd className="mt-1">
            <span className="font-medium tabular-nums">
              {t('spread.windFrom', {
                dir: from(f.wind.estimated_from_deg),
                kmh: Math.round(f.wind.estimated_speed_ms * KMH),
              })}
            </span>
            <span className="block text-ink-2 tabular-nums">
              {t('spread.windMeasured', {
                dir: from(f.wind.observed_from_deg),
                kmh: Math.round(f.wind.observed_speed_ms * KMH),
                source,
              })}
            </span>
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="eg-label">{t('spread.confidence')}</dt>
          <dd className="mt-1 tabular-nums">
            {t(`spread.conf.${conf}`)} ·{' '}
            {t('spread.scenarios', {
              pct: Math.round(f.confidence.ess_ratio * 100),
              n: f.confidence.members,
            })}
          </dd>
        </div>
      </dl>

      {f.closed && (
        <p className="rounded-md bg-ink/[0.05] px-3 py-2 text-sm text-ink-2">
          {t('spread.closed')}
        </p>
      )}
      <p className="text-sm text-ink-3">{t('spread.advisory')}</p>
    </div>
  )
}

/** What the sensors saw, and which ones should detect the fire next. */
export function SensorsOutlook({ forecast: f }: { forecast: Forecast }) {
  const { t } = useTranslation()
  return (
    <ul className="flex flex-col px-4 pb-4 text-sm">
      {f.observed.map((o) => (
        <li
          key={`${o.node_id}-${o.event}`}
          className="flex items-center gap-2 border-b border-line py-1.5"
        >
          <Icon name="flame" size={14} filled={o.event === 'FIRE'} className="text-ember" />
          <span className="font-semibold">
            {t('station.node')} {o.node_id}
          </span>
          <span className="text-ink-2">
            {o.event === 'FIRE' ? t('spread.detected') : t('spread.lost')}
          </span>
          <time dateTime={o.at} className="ms-auto text-ink-2 tabular-nums" dir="ltr">
            {formatClock(o.at)}
          </time>
        </li>
      ))}
      {f.next_nodes.map((n) => (
        <li
          key={`next-${n.node_id}`}
          className="flex items-center gap-2 border-b border-line py-1.5 last:border-b-0"
        >
          <Icon name="sensor" size={14} className="text-alert" />
          <span className="font-semibold">
            {t('station.node')} {n.node_id}
          </span>
          <span className="text-ink-2">{t('spread.expected')}</span>
          <span className="ms-auto text-end tabular-nums">
            <span dir="ltr">{etaLabel(n.eta_min)}</span>{' '}
            <span className="text-ink-2">
              · {t('spread.within1h', { pct: Math.round(n.p_within_60 * 100) })}
            </span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** Inhabited zones the fire may reach within 2 h: when, and how likely. */
export function ThreatenedZones({ forecast: f }: { forecast: Forecast }) {
  const { t, i18n } = useTranslation()
  return (
    <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
      {f.threatened_zones.length === 0 ? (
        <p className="text-ink-2">{t('spread.noZone')}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line rounded-md border border-line">
          {f.threatened_zones.map((z) => (
            <li key={z.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 px-3 py-2">
              <span dir="auto" className="font-semibold">
                {zoneLabel(
                  {
                    id: z.id,
                    name: z.name,
                    near: z.near,
                    population: z.population,
                    risk_level: z.risk_level,
                    risk_percentile: null,
                    building_count: 0,
                    tower_ids: [],
                  },
                  t,
                )}
              </span>
              <span className="text-ink-2 tabular-nums">
                {formatCount(z.population, i18n.language)} {t('spread.residents')}
              </span>
              <span className="ms-auto font-medium text-ember tabular-nums">
                {z.horizon_min === 0
                  ? t('spread.zoneNow', { pct: Math.round(z.p * 100) })
                  : t('spread.zoneWhen', { min: z.horizon_min, pct: Math.round(z.p * 100) })}
              </span>
            </li>
          ))}
        </ul>
      )}
      <Link
        to="/residents"
        className="flex min-h-10 items-center justify-center gap-2 rounded-md border border-line-strong font-semibold text-ink hover:bg-paper"
      >
        <Icon name="broadcast" size={16} />
        {t('spread.toResidents')}
      </Link>
    </div>
  )
}
