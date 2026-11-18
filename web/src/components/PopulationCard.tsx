import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import type { AlertProposal, Incident } from '../api/types'
import { formatClock, formatCount } from '../domain/time'
import { alertsSent } from '../domain/zones'
import { Card } from './Card'
import { Icon } from './Icon'

export interface ZonesSummary {
  zones: number
  people: number
  /** zones next to high fire risk */
  high: number
}

interface Props {
  /** the most urgent open fire, if any */
  fire: Incident | null
  /** who its public alert would reach */
  proposal: AlertProposal | undefined
  summary: ZonesSummary
}

/** Station page: the residents near the current fire and whether they were warned; the
 *  alert itself is prepared on the Residents tab. Without a fire, the zones being watched. */
export function PopulationCard({ fire, proposal, summary }: Props) {
  const { t, i18n } = useTranslation()
  const lng = i18n.language
  const sent = fire ? alertsSent(fire).at(-1) : undefined

  const link = (label: string) => (
    <Link
      to="/residents"
      className="mx-4 flex min-h-10 items-center justify-center gap-2 rounded-md border border-line-strong text-sm font-semibold text-ink hover:bg-paper"
    >
      <Icon name="broadcast" size={16} />
      {label}
    </Link>
  )

  if (!fire) {
    return (
      <Card title={t('populationCard.title')} className="gap-3 pb-4">
        <dl className="mx-4 grid grid-cols-3 gap-2">
          {(
            [
              ['populationCard.zones', String(summary.zones)],
              ['populationCard.residents', formatCount(summary.people, lng)],
              ['populationCard.highRisk', String(summary.high)],
            ] as const
          ).map(([key, value]) => (
            <div key={key} className="rounded-md bg-paper px-3 py-2">
              <dt className="text-xs text-ink-2">{t(key)}</dt>
              <dd className="text-xl font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
        {link(t('populationCard.open'))}
      </Card>
    )
  }

  const zones = proposal?.zones ?? []
  return (
    <Card title={t('populationCard.title')} className="gap-3 pb-4">
      {!proposal ? (
        <p className="px-4 text-sm text-ink-2">{t('population.loading')}</p>
      ) : zones.length === 0 ? (
        <p className="px-4 text-sm text-ink-2">
          {t('population.none', { km: proposal.radius_km })}
        </p>
      ) : (
        <>
          <p className="flex items-baseline gap-2 px-4">
            <span className="text-2xl font-semibold tabular-nums">
              {formatCount(proposal.people, lng)}
            </span>
            <span className="text-sm text-ink-2">
              {t('populationCard.near', { km: proposal.radius_km })}
            </span>
          </p>
          <ul className="mx-4 flex flex-col divide-y divide-line rounded-md border border-line text-sm">
            {zones.slice(0, 3).map((z) => (
              <li key={z.id} className="flex items-center gap-2 px-3 py-1.5">
                <span lang="ar" dir="rtl" className="font-medium">
                  {z.label}
                </span>
                <span dir="ltr" className="ms-auto text-ink-2 tabular-nums">
                  {z.distance_km.toFixed(1)} km
                </span>
                <span className="w-14 text-end tabular-nums">{formatCount(z.population, lng)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      {sent ? (
        <p className="mx-4 flex items-center gap-2 rounded-md bg-ok-soft px-3 py-2 text-sm font-medium text-ok">
          <Icon name="check" size={16} strokeWidth={2.25} />
          {t('population.sentAt', { time: formatClock(sent.ts) })}
        </p>
      ) : (
        zones.length > 0 && (
          <p className="mx-4 rounded-md bg-alert-soft px-3 py-2 text-sm font-medium text-alert">
            {t('populationCard.notSent')}
          </p>
        )
      )}
      {zones.length > 0 && link(sent ? t('populationCard.open') : t('populationCard.prepare'))}
    </Card>
  )
}
