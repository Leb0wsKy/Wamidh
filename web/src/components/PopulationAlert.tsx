import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AlertProposal, Incident } from '../api/types'
import { formatClock, formatCount } from '../domain/time'
import { alertsSent, broadcastBlock } from '../domain/zones'
import { Icon } from './Icon'

interface Props {
  incident: Incident
  /** who the alert would reach; undefined while loading */
  proposal: AlertProposal | undefined
  onSend: () => void
  sending?: boolean
  /** the backend refused the broadcast */
  error?: string | null
}

const RISK_DOT: Record<string, string> = {
  high: 'bg-ember',
  medium: 'bg-alert-fill',
  low: 'bg-ink-3',
}

/**
 * The incident's "Population" section: the inhabited zones near the fire, the Arabic Cell
 * Broadcast text, and the dispatcher's button. Nothing is sent without a confirmation.
 */
export function PopulationAlert({ incident, proposal, onSend, sending = false, error }: Props) {
  const { t, i18n } = useTranslation()
  const [confirming, setConfirming] = useState(false)
  const lng = i18n.language
  const zones = proposal?.zones ?? []
  const block = broadcastBlock(incident, zones.length)
  const sent = alertsSent(incident)
  const last = sent.at(-1)
  const people = formatCount(proposal?.people ?? 0, lng)

  return (
    <section aria-labelledby="population-title" className="flex flex-col gap-4">
      <h3 id="population-title" className="eg-label">
        {t('population.title')}
      </h3>

      {!proposal ? (
        <p className="text-ink-2">{t('population.loading')}</p>
      ) : zones.length === 0 ? (
        <p className="text-ink-2">{t('population.none', { km: proposal.radius_km })}</p>
      ) : (
        <>
          <dl className="grid grid-cols-3 gap-4">
            {(
              [
                ['population.residents', people],
                ['population.zones', String(zones.length)],
                ...(proposal.tower_ids.length > 0
                  ? [['population.towers', String(proposal.tower_ids.length)] as const]
                  : []),
              ] as const
            ).map(([key, value]) => (
              <div key={key}>
                <dt className="eg-label">{t(key)}</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          {proposal.tower_ids.length === 0 && (
            <p className="text-sm text-ink-2">{t('population.byOutline')}</p>
          )}
          <ul className="divide-y divide-line rounded-md border border-line">
            {zones.map((z) => (
              <li key={z.id} className="flex items-center gap-3 px-3 py-2">
                <span aria-hidden className={`size-2.5 rounded-full ${RISK_DOT[z.risk_level]}`} />
                <span lang="ar" dir="rtl" className="font-medium">
                  {z.label}
                </span>
                <span dir="ltr" className="ms-auto text-ink-2 tabular-nums">
                  {z.distance_km.toFixed(1)} km
                </span>
                <span className="w-28 text-end tabular-nums">
                  {t('population.people', { n: formatCount(z.population, lng) })}
                </span>
              </li>
            ))}
          </ul>
          <figure
            lang="ar"
            dir="rtl"
            className="rounded-md border border-line bg-paper px-4 py-3 leading-relaxed"
          >
            <figcaption className="eg-label mb-1" lang={lng} dir="auto">
              {t('population.preview')}
            </figcaption>
            <p className="font-semibold">{proposal.headline}</p>
            <p>{proposal.description}</p>
            <p>{proposal.instruction}</p>
          </figure>
        </>
      )}

      {last && (
        <p role="status" className="flex items-center gap-2 font-medium text-ok">
          <Icon name="check" size={18} />
          {t('population.sentAt', { time: formatClock(last.ts) })}
        </p>
      )}

      {confirming && !block ? (
        <div className="flex flex-col gap-3 rounded-md border-2 border-ember bg-ember-soft p-4">
          <p className="font-medium">{t('population.confirmText', { people })}</p>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={sending}
              onClick={() => {
                setConfirming(false)
                onSend()
              }}
              className="min-h-12 flex-1 rounded-md bg-ember px-4 font-bold text-white hover:bg-ember-deep focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-60"
            >
              {t('population.confirm', { people })}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              className="min-h-12 rounded-md border border-line-strong bg-surface px-4 font-medium"
            >
              {t('population.cancel')}
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          disabled={block !== null || sending || !proposal}
          onClick={() => setConfirming(true)}
          className={`flex min-h-12 items-center justify-center gap-2 rounded-md px-4 text-lg font-bold focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:cursor-not-allowed disabled:opacity-50 ${
            last
              ? 'border border-line-strong bg-surface text-ink hover:bg-paper'
              : 'bg-ink text-white hover:bg-ink/85'
          }`}
        >
          <Icon name="broadcast" size={20} />
          {last ? t('population.update') : t('population.broadcast')}
        </button>
      )}
      {block === 'ack' && <p className="text-ink-2">{t('population.needsAck')}</p>}
      {error && (
        <p role="alert" className="text-ember">
          {error}
        </p>
      )}
      <p className="text-sm text-ink-3">{t('population.note')}</p>
    </section>
  )
}
