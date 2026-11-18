import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAllIncidents, useForecast, useNodes, useZones } from '../api/queries'
import type { Incident } from '../api/types'
import { Card } from '../components/Card'
import { SpreadMap } from '../components/SpreadMap'
import { SensorsOutlook, SpreadSummary, ThreatenedZones } from '../components/SpreadSummary'
import { dispatchOrder, isOpen } from '../domain/incident'
import { HORIZONS, type Horizon } from '../domain/spread'
import { formatCount, formatDateTime } from '../domain/time'

const RECENT_CLOSED = 3

/**
 * Propagation tab: where each fire is likely to be within the next two hours, from the physics
 * ensemble corrected by the sensors' alerts (ADR 0004). Advisory: decisions stay with crews.
 */
export function SpreadPage() {
  const { t, i18n } = useTranslation()
  const all = dispatchOrder(useAllIncidents().data ?? [])
  // Burning fires first, then the last few closed ones (their forecast is kept for review).
  const fires: Incident[] = [
    ...all.filter((i) => isOpen(i.status)),
    ...all.filter((i) => !isOpen(i.status)).slice(0, RECENT_CLOSED),
  ]
  const [chosen, setChosen] = useState<number | null>(null)
  const fire = fires.find((f) => f.id === chosen) ?? fires.find((f) => isOpen(f.status)) ?? null
  const query = useForecast(fire?.id ?? null)
  const forecast = query.data?.incident_id === fire?.id ? query.data : undefined
  const nodes = useNodes().data ?? []
  const zones = useZones().data?.features ?? []
  const [horizon, setHorizon] = useState<Horizon>(60)

  return (
    <div className="grid h-full grid-cols-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_26rem] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden">
      <Card className="h-[65vh] overflow-hidden lg:h-auto">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-3 pb-3">
          <h1 className="text-lg font-semibold text-ink">{t('spread.title')}</h1>
          {forecast && (
            <div
              role="radiogroup"
              aria-label={t('spread.time')}
              className="flex overflow-hidden rounded-md border border-line-strong"
            >
              {HORIZONS.map((h) => (
                <button
                  key={h}
                  type="button"
                  role="radio"
                  aria-checked={horizon === h}
                  onClick={() => setHorizon(h)}
                  className={`min-h-9 border-e border-line px-3 text-sm font-medium tabular-nums last:border-e-0 ${
                    horizon === h ? 'bg-ink text-white' : 'bg-surface text-ink-2 hover:text-ink'
                  }`}
                >
                  {h === 0 ? t('spread.now') : t('spread.plus', { min: h })}
                </button>
              ))}
            </div>
          )}
          {forecast && (
            <p className="text-sm text-ink-2 tabular-nums">
              {t('spread.burnedBy', {
                ha: formatCount(forecast.area_ha[String(horizon)] ?? 0, i18n.language),
              })}
            </p>
          )}
        </div>
        <div className="relative min-h-0 flex-1 border-t border-line">
          <SpreadMap forecast={forecast} horizon={horizon} nodes={nodes} zones={zones} />
          {forecast && (
            <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] rounded-md border border-line-strong bg-surface px-3 py-2 text-xs shadow-sm">
              <p className="mb-1 font-medium text-ink">{t('spread.legend')}</p>
              <div className="flex items-center gap-3">
                {[
                  ['≥ 20 %', 'bg-ember/15 border-dashed'],
                  ['≥ 50 %', 'bg-ember/30'],
                  ['≥ 80 %', 'bg-ember/55'],
                ].map(([label, cls]) => (
                  <span key={label} className="flex items-center gap-1.5 tabular-nums">
                    <span
                      aria-hidden
                      className={`inline-block size-3 rounded-sm border border-ember ${cls}`}
                    />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      <div className="flex flex-col gap-4 lg:overflow-y-auto">
        {fires.length === 0 ? (
          <Card title={t('spread.title')}>
            <p className="px-4 pb-4 text-ink-2">{t('spread.noFire')}</p>
          </Card>
        ) : (
          <Card
            title={t('spread.fire')}
            className={fire && isOpen(fire.status) ? 'border-ember' : ''}
          >
            <div className="flex flex-wrap gap-2 px-4 pb-3" role="tablist">
              {fires.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  role="tab"
                  aria-selected={f.id === fire?.id}
                  onClick={() => setChosen(f.id)}
                  className={`min-h-9 rounded-md border px-3 text-sm font-medium ${
                    f.id === fire?.id
                      ? 'border-ember bg-ember-soft text-ink'
                      : isOpen(f.status)
                        ? 'border-line-strong bg-surface text-ink'
                        : 'border-line bg-surface text-ink-3'
                  }`}
                >
                  {t('station.node')} {f.first_node_id} <span dir="ltr">#{f.id}</span>
                  {!isOpen(f.status) && (
                    <span className="ms-1 text-xs text-ink-3 tabular-nums">
                      {formatDateTime(f.created_at)}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {forecast ? (
              <SpreadSummary forecast={forecast} />
            ) : (
              <p className="px-4 pb-4 text-ink-2">
                {query.isError ? t('spread.unavailable') : t('spread.loading')}
              </p>
            )}
          </Card>
        )}
        {forecast && (
          <>
            <Card title={t('spread.zones')}>
              <ThreatenedZones forecast={forecast} />
            </Card>
            <Card title={t('spread.sensors')}>
              <SensorsOutlook forecast={forecast} />
            </Card>
          </>
        )}
      </div>
    </div>
  )
}
