import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import type { SensorNode } from '../api/types'
import { nodeStyle } from '../domain/nodeState'
import { readingTone, type Tone } from '../domain/readings'
import { shortAgo, timeUnits } from '../domain/status'
import { formatDateTime } from '../domain/time'
import { directionOf } from '../i18n'
import { BatteryGauge } from './BatteryGauge'
import { Icon } from './Icon'

interface Props {
  node: SensorNode
  now: number
  onClose: () => void
}

// A tile is quiet while its reading is normal; amber or ember only when it points to fire.
const TILE: Record<Tone, string> = {
  normal: 'border-line bg-paper text-ink',
  alert: 'border-alert-fill/60 bg-alert-soft text-alert',
  fire: 'border-ember/40 bg-ember-soft text-ember',
}
const BAR: Record<Tone, string> = { normal: 'bg-ink-3', alert: 'bg-alert-fill', fire: 'bg-ember' }

function Tile({
  name,
  label,
  tone,
  children,
}: {
  name: string
  label: string
  tone: Tone
  children: ReactNode
}) {
  return (
    <div
      data-testid={`tile-${name}`}
      data-tone={tone}
      className={`flex min-w-0 flex-col gap-0.5 rounded-md border px-2.5 py-2 ${TILE[tone]}`}
    >
      <span className="truncate text-[11px] font-medium text-ink-2">{label}</span>
      {children}
    </div>
  )
}

/** The popup for one sensor on the station map. */
export function SensorDetails({ node, now, onClose }: Props) {
  const { t, i18n } = useTranslation()
  const s = nodeStyle(node.state)
  const r = node.readings ?? {}
  const ago = (iso: string) => t('popup.ago', { t: shortAgo(now - Date.parse(iso), timeUnits(t)) })
  const when = (iso: string | null | undefined) =>
    iso ? `${formatDateTime(iso)} · ${ago(iso)}` : t('popup.never')
  const tone = {
    temp: readingTone('temp', r.temp_c),
    rh: readingTone('rh', r.rh_pct),
    gas: readingTone('gas', r.gas_ratio),
    flame: readingTone('flame', r.flame),
    ai: readingTone('ai', r.fire_prob),
  }
  const value = 'text-start text-lg leading-tight font-semibold tabular-nums'

  return (
    // The map is always left-to-right; the popup follows the interface language.
    <div dir={directionOf(i18n.language)} className="w-80 text-sm">
      <header
        className="flex items-center gap-2 border-b border-line px-3 py-2.5"
        style={{ borderTop: `3px solid ${s.color}` }}
      >
        <h3 className="text-base font-bold text-ink">
          {t('station.node')} {node.id}
        </h3>
        <span className="font-semibold" style={{ color: s.color }}>
          {t(s.labelKey)}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('popup.close')}
          className="ms-auto grid size-8 place-items-center rounded-md text-ink-2 hover:bg-paper hover:text-ink"
        >
          <Icon name="close" size={18} />
        </button>
      </header>

      <div className="flex flex-col gap-2.5 px-3 py-2.5">
        <section className="flex flex-col gap-1.5" aria-label={t('popup.readings')}>
          <div className="grid grid-cols-3 gap-1.5">
            <Tile name="temp" label={t('popup.temp')} tone={tone.temp}>
              <span dir="ltr" className={value}>
                {r.temp_c != null ? `${r.temp_c.toFixed(1)} °C` : '—'}
              </span>
            </Tile>
            <Tile name="rh" label={t('card.humidity')} tone={tone.rh}>
              <span dir="ltr" className={value}>
                {r.rh_pct != null ? `${Math.round(r.rh_pct)} %` : '—'}
              </span>
            </Tile>
            <Tile name="gas" label={t('card.gas')} tone={tone.gas}>
              <span className="flex items-baseline gap-1.5">
                <span className={value}>{r.gas_ratio != null ? r.gas_ratio.toFixed(2) : '—'}</span>
                {/* Smoke lowers the gas ratio below the node's clean-air baseline (1.00). */}
                {tone.gas !== 'normal' && (
                  <span className="text-[11px] font-semibold">{t('popup.smoke')}</span>
                )}
              </span>
            </Tile>
          </div>
          <div className="grid grid-cols-[1fr_2fr] gap-1.5">
            <Tile name="flame" label={t('popup.flame')} tone={tone.flame}>
              <span className={`flex items-center gap-1 ${value}`}>
                {r.flame && <Icon name="flame" size={16} filled />}
                {r.flame == null ? '—' : r.flame ? t('popup.yes') : t('popup.no')}
              </span>
            </Tile>
            <Tile name="ai" label={t('ledger.ai')} tone={tone.ai}>
              <span dir="ltr" className={value}>
                {r.fire_prob != null ? `${Math.round(r.fire_prob * 100)} %` : '—'}
              </span>
              <span aria-hidden className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-line">
                {r.fire_prob != null && (
                  <span
                    className={`block h-full rounded-full ${BAR[tone.ai]}`}
                    style={{ width: `${Math.max(2, r.fire_prob * 100)}%` }}
                  />
                )}
              </span>
            </Tile>
          </div>
        </section>

        <section>
          <h4 className="eg-label mb-1">{t('popup.location')}</h4>
          <p dir="ltr" className="text-start text-ink tabular-nums">
            {node.lat.toFixed(5)}, {node.lon.toFixed(5)}
          </p>
          <p className="flex flex-wrap gap-x-2 text-ink-2">
            {node.access_point && (
              <span>
                {t('popup.access', {
                  road: t(`roadType.${node.access_point.road_type}`, {
                    defaultValue: node.access_point.road_type,
                  }),
                })}
              </span>
            )}
            <span>
              {node.gateway_id !== null
                ? t('popup.gateway', { id: node.gateway_id })
                : t('card.noLink')}
            </span>
          </p>
        </section>

        <section>
          <h4 className="eg-label mb-1">{t('popup.history')}</h4>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-0.5">
            <dt className="text-ink-2">{t('popup.lastAlert')}</dt>
            <dd className="text-end font-medium text-ink tabular-nums">
              {when(node.last_alert_at)}
            </dd>
            <dt className="text-ink-2">{t('popup.lastFire')}</dt>
            <dd className="text-end font-medium text-ink tabular-nums">
              {when(node.last_fire_at)}
            </dd>
          </dl>
        </section>

        <section className="flex items-center gap-3 border-t border-line pt-2.5 text-xs text-ink-2">
          <span className="eg-label">{t('popup.health')}</span>
          <BatteryGauge volts={node.battery_v} />
          {node.link && node.link.lost > 0 && <span>{t('card.lost', { n: node.link.lost })}</span>}
          <span className="ms-auto tabular-nums" title={t('ledger.contact')}>
            {node.last_seen ? ago(node.last_seen) : t('station.never')}
          </span>
        </section>
      </div>
    </div>
  )
}
