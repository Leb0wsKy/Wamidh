import { useTranslation } from 'react-i18next'
import type { Incident, SensorNode } from '../api/types'
import type { Spread } from '../domain/incident'
import { situation, type Situation } from '../domain/overview'
import { formatElapsed, shortAgo, timeUnits } from '../domain/status'
import { Card } from './Card'
import { Icon } from './Icon'

interface Props {
  /** open incidents, in dispatch order */
  incidents: Incident[]
  nodes: SensorNode[]
  soundLocked: boolean
  spread: Spread | null
  now: number
}

const LEVEL: Record<Situation['level'], { dot: string; text: string; key: string }> = {
  normal: { dot: 'bg-ok', text: 'text-ink', key: 'overview.normal' },
  alert: { dot: 'bg-alert-fill', text: 'text-alert', key: 'overview.alert' },
  fire: { dot: 'bg-ember eg-pulse', text: 'text-ember', key: 'overview.fire' },
}

function Figure({
  id,
  label,
  value,
  tone = 'text-ink',
}: {
  id: string
  label: string
  value: string
  tone?: string
}) {
  return (
    <div data-testid={`fig-${id}`} className="flex flex-col gap-0.5 rounded-md bg-paper px-3 py-2">
      <span className="text-[11px] font-medium text-ink-2">{label}</span>
      <span
        dir="ltr"
        className={`text-start text-2xl leading-none font-semibold tabular-nums ${tone}`}
      >
        {value}
      </span>
    </div>
  )
}

/** The station's situation at a glance: headline, key figures, network, power and siren. */
export function SituationCard({ incidents, nodes, soundLocked, spread, now }: Props) {
  const { t, i18n } = useTranslation()
  const s = situation(nodes, incidents)
  const lvl = LEVEL[s.level]
  const burning = incidents.find((i) => i.status !== 'UNDER_CONTROL')
  // Western digits in every language, like the rest of the interface.
  const num = (v: number, digits: number) =>
    v.toLocaleString(i18n.language === 'ar' ? 'en' : i18n.language, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })

  return (
    <Card className="gap-3 p-4">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2.5">
          <span aria-hidden className={`inline-block size-3 rounded-full ${lvl.dot}`} />
          <h2 className={`text-xl font-semibold ${lvl.text}`}>{t(lvl.key)}</h2>
        </div>
        {spread ? (
          <p role="status" className="flex items-center gap-1.5 text-sm font-semibold text-alert">
            <Icon name="flame" size={16} />
            {t('station.spreadBanner', { node: spread.nodeId, id: spread.incidentId })}
          </p>
        ) : (
          burning && (
            <p className="text-sm text-ink-2">
              {t('station.fireAt', { node: burning.first_node_id })} ·{' '}
              <span className="tabular-nums">
                {t('station.since', { t: formatElapsed(now - Date.parse(burning.created_at)) })}
              </span>
            </p>
          )
        )}
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Figure
          id="sensors"
          label={t('overview.sensors')}
          value={`${s.online}/${s.total}`}
          tone={s.online < s.total ? 'text-alert' : 'text-ink'}
        />
        <Figure
          id="alerts"
          label={t('overview.alerts')}
          value={String(s.alerts)}
          tone={s.alerts > 0 ? 'text-alert' : 'text-ink'}
        />
        <Figure
          id="fires"
          label={t('overview.fires')}
          value={String(s.fires)}
          tone={s.fires > 0 ? 'text-ember' : 'text-ink'}
        />
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-ink-2">{t('overview.network')}</dt>
        <dd className="text-end">
          <span className="font-semibold">{t('overview.gateways', { n: s.gateways })}</span>
          <span className="text-ink-2"> · {t('overview.loss', { p: num(s.lossPct, 1) })}</span>
        </dd>
        <dt className="text-ink-2">{t('overview.power')}</dt>
        <dd dir="ltr" className="text-end tabular-nums">
          {s.batteryMin !== null && s.batteryAvg !== null ? (
            <>
              <span className="text-ink-2">{t('overview.min')} </span>
              <span className="font-semibold">{num(s.batteryMin, 2)} V</span>
              <span className="text-ink-2">
                {' '}
                · {t('overview.avg')} {num(s.batteryAvg, 2)} V
              </span>
            </>
          ) : (
            '—'
          )}
        </dd>
      </dl>

      <div className="flex items-center gap-3 border-t border-line pt-3 text-sm">
        {soundLocked ? (
          // No handler needed: any click on the page unlocks audio (useAlarm).
          <button
            type="button"
            className="flex h-8 items-center gap-2 rounded-md border border-alert px-3 font-semibold text-alert hover:bg-alert-soft"
          >
            <Icon name="speakerOff" size={16} />
            {t('station.armSiren')}
          </button>
        ) : (
          <span className="flex items-center gap-2 text-ink-2">
            <Icon name="siren" size={16} />
            {t('station.sirenArmed')}
          </span>
        )}
        {s.lastReport && (
          <span className="ms-auto text-ink-2 tabular-nums">
            {t('overview.lastReport', {
              t: shortAgo(now - Date.parse(s.lastReport), timeUnits(t)),
            })}
          </span>
        )}
      </div>
    </Card>
  )
}
