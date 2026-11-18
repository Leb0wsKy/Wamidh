import { useTranslation } from 'react-i18next'
import type { Incident, SensorNode } from '../api/types'
import { formatElapsed } from '../domain/status'
import { formatDateTime } from '../domain/time'
import { activity24h, watchItems, type WatchItem } from '../domain/watch'
import { Card } from './Card'
import { Icon } from './Icon'

interface Props {
  nodes: SensorNode[]
  /** every incident, closed ones included */
  incidents: Incident[]
  now: number
}

/** Maintenance worth a look, and what happened in the last 24 hours. */
export function WatchCard({ nodes, incidents, now }: Props) {
  const { t } = useTranslation()
  const items = watchItems(nodes)
  const a = activity24h(incidents, nodes, now)

  const detail = (i: WatchItem): string => {
    switch (i.kind) {
      case 'lost':
        return t('nodeState.LOST_PROBABLY_BURNED')
      case 'silent':
        return i.since
          ? t('card.silent', { t: formatElapsed(now - Date.parse(i.since)) })
          : t('station.never')
      case 'battery':
        return t('watch.lowBattery', { v: (i.value ?? 0).toFixed(2) })
      case 'radio':
        return t('overview.loss', { p: (i.value ?? 0).toFixed(1) })
    }
  }

  return (
    <Card title={t('watch.title')} className="pb-3">
      {items.length === 0 ? (
        <p className="mx-4 flex items-center gap-2 rounded-md bg-ok-soft px-3 py-2 text-sm font-medium text-ok">
          <Icon name="check" size={16} strokeWidth={2.25} />
          {t('watch.ok')}
        </p>
      ) : (
        <ul className="mx-4 flex flex-col divide-y divide-line rounded-md border border-line text-sm">
          {items.map((i) => (
            <li key={`${i.nodeId}-${i.kind}`} className="flex items-center gap-2 px-3 py-2">
              <Icon
                name={i.kind === 'battery' ? 'battery' : i.kind === 'radio' ? 'gateway' : 'sensor'}
                size={16}
                className={i.kind === 'lost' || i.kind === 'silent' ? 'text-ink' : 'text-alert'}
              />
              <span className="font-semibold text-ink">
                {t('station.node')} {i.nodeId}
              </span>
              <span className="ms-auto text-ink-2 tabular-nums">{detail(i)}</span>
            </li>
          ))}
        </ul>
      )}

      <h3 className="eg-label px-4 pt-4 pb-2">{t('watch.day')}</h3>
      <div className="mx-4 grid grid-cols-3 gap-2 text-center">
        {(
          [
            ['act-fires', t('overview.fires'), a.fires, a.fires > 0 ? 'text-ember' : 'text-ink'],
            ['act-false', t('watch.falseAlarms'), a.falseAlarms, 'text-ink'],
            [
              'act-alerted',
              t('watch.alerted'),
              a.alertedSensors,
              a.alertedSensors > 0 ? 'text-alert' : 'text-ink',
            ],
          ] as const
        ).map(([id, label, n, tone]) => (
          <div
            key={id}
            data-testid={id}
            className="flex flex-col gap-0.5 rounded-md bg-paper px-2 py-2"
          >
            <span className={`text-xl leading-none font-semibold tabular-nums ${tone}`}>{n}</span>
            <span className="text-[11px] text-ink-2">{label}</span>
          </div>
        ))}
      </div>
      <p className="mx-4 mt-2 text-sm text-ink-2">
        {a.lastFire
          ? t('watch.lastFire', { node: a.lastFire.nodeId, t: formatDateTime(a.lastFire.at) })
          : t('watch.noFire')}
      </p>
    </Card>
  )
}
