import { useTranslation } from 'react-i18next'
import type { SensorNode } from '../api/types'
import { nodeStyle } from '../domain/nodeState'
import { readingTone } from '../domain/readings'
import { formatElapsed } from '../domain/status'
import { sparkPath } from '../domain/trend'
import { BatteryGauge } from './BatteryGauge'
import { Icon } from './Icon'

interface Props {
  /** the rows to show, already chosen and ordered (domain/ledger.ts) */
  nodes: SensorNode[]
  /** sensors matching: all installed ones, or the search results */
  total: number
  /** the number typed in the search field */
  query: string
  onQuery: (query: string) => void
  now: number
  /** recent temperatures per sensor, oldest first */
  trends: Record<number, number[]>
  trendMinutes: number
  /** sensor under the pointer (here, on the map or on the timeline) */
  highlightId: number | null
  onHover: (nodeId: number | null) => void
  /** centre the map on this sensor */
  onSelect: (nodeId: number) => void
}

const STATE_TEXT: Record<SensorNode['state'], string> = {
  NORMAL: 'text-ink-2',
  ALERT: 'font-semibold text-alert',
  FIRE: 'font-semibold text-ember',
  OFFLINE: 'font-medium text-ink',
  LOST_PROBABLY_BURNED: 'font-medium text-ink',
}
const COLS =
  'grid grid-cols-[1.5rem_5rem_minmax(5.5rem,auto)_minmax(3rem,1fr)_3.25rem_4.75rem_5.5rem] items-center gap-x-3'
const AI_TONE = {
  normal: 'text-ink',
  alert: 'font-semibold text-alert',
  fire: 'font-bold text-ember',
}
const SPARK_W = 120
const SPARK_H = 22

/** The sensors as a dense ledger: one row each, with a short trend, and a search by number. */
export function SensorLedger({
  nodes,
  total,
  query,
  onQuery,
  now,
  trends,
  trendMinutes,
  highlightId,
  onHover,
  onSelect,
}: Props) {
  const { t } = useTranslation()
  const rows = nodes
  const searching = query.trim() !== ''

  function contact(n: SensorNode): string {
    if (!n.last_seen) return t('station.never')
    const ms = now - Date.parse(n.last_seen)
    if (n.state === 'OFFLINE' || n.state === 'LOST_PROBABLY_BURNED')
      return t('card.silent', { t: formatElapsed(ms) })
    return ms < 120_000
      ? t('station.ago', { s: Math.max(0, Math.round(ms / 1000)) })
      : t('station.agoMin', { m: Math.round(ms / 60_000) })
  }

  return (
    <div className="text-sm">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 pb-3">
        <label className="relative flex items-center">
          <span className="sr-only">{t('ledger.search')}</span>
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            className="pointer-events-none absolute start-2.5 size-4 text-ink-3"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          >
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4.5 4.5" />
          </svg>
          <input
            type="search"
            inputMode="numeric"
            aria-label={t('ledger.search')}
            placeholder={t('ledger.searchPlaceholder')}
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            className="h-9 w-48 rounded-md border border-line-strong bg-surface ps-8 pe-2 text-sm text-ink tabular-nums placeholder:text-ink-3 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ink"
          />
        </label>
        <p className="text-xs text-ink-2">
          {!searching
            ? t('ledger.topRisk', { n: rows.length, total })
            : total === 0
              ? t('ledger.noMatch', { q: query.trim() })
              : t('ledger.matches', { n: rows.length, total, q: query.trim() })}
        </p>
      </div>
      <div
        className={`${COLS} border-b border-line-strong px-3 pb-2 text-[11px] font-medium text-ink-2`}
      >
        <span>#</span>
        <span>{t('ledger.state')}</span>
        <span>{t('ledger.reading')}</span>
        <span>{t('ledger.trend', { n: trendMinutes })}</span>
        <span className="text-end">{t('ledger.ai')}</span>
        <span>{t('ledger.battery')}</span>
        <span className="text-end">{t('ledger.contact')}</span>
      </div>
      {rows.map((n) => {
        const s = nodeStyle(n.state)
        const r = n.readings ?? {}
        const fire = n.state === 'FIRE'
        const silent = n.state === 'OFFLINE' || n.state === 'LOST_PROBABLY_BURNED'
        const prob = r.fire_prob
        const path = sparkPath(trends[n.id] ?? [], SPARK_W, SPARK_H)
        return (
          <button
            key={n.id}
            type="button"
            aria-label={`${t('station.node')} ${n.id} · ${t(s.labelKey)}`}
            onClick={() => onSelect(n.id)}
            onMouseEnter={() => onHover(n.id)}
            onMouseLeave={() => onHover(null)}
            onFocus={() => onHover(n.id)}
            onBlur={() => onHover(null)}
            className={`${COLS} relative w-full border-b border-line px-3 py-2.5 text-start ${
              fire ? 'bg-ember-soft' : n.id === highlightId ? 'bg-surface' : 'hover:bg-surface'
            } ${silent ? 'text-ink-2' : ''}`}
          >
            <span
              aria-hidden
              className={`absolute inset-y-1 start-0 w-[3px] rounded-full ${s.pulse ? 'eg-pulse' : ''}`}
              style={{ background: s.color }}
            />
            <span
              className={`text-base font-bold tabular-nums ${n.id === highlightId ? 'underline decoration-2 underline-offset-4' : ''}`}
            >
              {n.id}
            </span>
            <span className={STATE_TEXT[n.state]}>
              {t(s.labelKey)}
              {r.flame && (
                <Icon
                  name="flame"
                  size={13}
                  filled
                  className="ms-1 inline align-[-2px] text-ember"
                />
              )}
            </span>
            <span className="flex flex-col leading-tight">
              <span dir="ltr" className="text-start text-base font-semibold text-ink tabular-nums">
                {r.temp_c != null ? `${r.temp_c.toFixed(1)} °C` : '—'}
              </span>
              <span dir="ltr" className="text-start text-[11px] text-ink-2 tabular-nums">
                {r.rh_pct != null && r.gas_ratio != null
                  ? `${Math.round(r.rh_pct)} % · ${t('ledger.gas')} ${r.gas_ratio.toFixed(2)}`
                  : ''}
              </span>
            </span>
            <svg
              aria-hidden
              viewBox={`-1 -2 ${SPARK_W + 2} ${SPARK_H + 4}`}
              preserveAspectRatio="none"
              className="h-6 w-full"
            >
              {path && (
                <path
                  d={path}
                  fill="none"
                  stroke={fire ? 'var(--color-ember)' : 'var(--color-ink-2)'}
                  strokeWidth={1.5}
                  vectorEffect="non-scaling-stroke"
                  strokeLinejoin="round"
                />
              )}
            </svg>
            <span
              dir="ltr"
              className={`text-end tabular-nums ${prob == null ? 'text-ink-3' : AI_TONE[readingTone('ai', prob)]}`}
            >
              {prob != null ? `${Math.round(prob * 100)} %` : '—'}
            </span>
            <span className="text-xs">
              <BatteryGauge volts={n.battery_v} />
            </span>
            <span className="flex flex-col items-end text-xs leading-tight text-ink-2 tabular-nums">
              <span>{contact(n)}</span>
              {n.gateway_id === null ? (
                <span className="font-medium text-alert">{t('card.noLink')}</span>
              ) : n.link && n.link.lost > 0 ? (
                <span>{t('card.lost', { n: n.link.lost })}</span>
              ) : null}
            </span>
          </button>
        )
      })}
    </div>
  )
}
