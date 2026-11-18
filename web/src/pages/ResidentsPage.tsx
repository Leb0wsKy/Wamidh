import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useAlertProposal,
  useOpenIncidents,
  usePublicAlerts,
  useSendAlert,
  useTowers,
  useZones,
} from '../api/queries'
import { Card } from '../components/Card'
import { FireAlertPanel } from '../components/FireAlertPanel'
import { PhoneAlertCard } from '../components/PhoneAlertCard'
import { ZonePanel } from '../components/ZonePanel'
import { ZonesMap, type FireFocus } from '../components/ZonesMap'
import { ALERTS } from '../config'
import { dispatchOrder } from '../domain/incident'
import { formatCount } from '../domain/time'
import { zoneAlert } from '../domain/zones'

const LEGEND = [
  { key: 'high', className: 'bg-ember/60 border-ember' },
  { key: 'medium', className: 'bg-alert-fill/60 border-alert-fill' },
  { key: 'low', className: 'bg-ink-3/40 border-ink-3' },
] as const

/**
 * Residents tab (public): the inhabited zones around the forest, the fire risk next to them,
 * the cell towers that would carry an alert, and the alerts in progress as phones show them.
 * No sensor or personal data here.
 */
export function ResidentsPage() {
  const { t, i18n } = useTranslation()
  const zones = useZones().data?.features ?? []
  const towers = useTowers().data?.features ?? []
  const alerts = usePublicAlerts(true, ALERTS.refreshMs).data ?? []
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const selected = zones.find((z) => z.properties.id === selectedId)
  const alerted = new Set(alerts.flatMap((a) => a.zones.map((z) => z.id)))
  const people = zones.reduce((sum, z) => sum + z.properties.population, 0)
  // Open fires: the dispatcher prepares and broadcasts their public alert here.
  const fires = dispatchOrder(useOpenIncidents().data ?? [])
  const [chosenFire, setChosenFire] = useState<number | null>(null)
  const fireIncident = fires.find((f) => f.id === chosenFire) ?? fires[0] ?? null
  const proposal = useAlertProposal(fireIncident?.id ?? null).data
  const send = useSendAlert()
  const origin = fireIncident?.estimated_origin
  const fire: FireFocus | null =
    fireIncident && origin
      ? { id: fireIncident.id, ...origin, radiusM: (proposal?.radius_km ?? 0) * 1000 }
      : null
  const concerned = new Set(proposal?.zones.map((z) => z.id) ?? [])

  return (
    <div className="grid h-full grid-cols-1 gap-4 overflow-y-auto p-4 lg:grid-cols-[minmax(0,1fr)_25rem] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden">
      <Card className="h-[65vh] overflow-hidden lg:h-auto">
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 px-4 pt-3.5 pb-3">
          <h1 className="text-lg font-semibold text-ink">{t('residents.title')}</h1>
          <p className="text-sm text-ink-2 tabular-nums">
            {t(towers.length > 0 ? 'residents.stats' : 'residents.statsNoTowers', {
              zones: zones.length,
              people: formatCount(people, i18n.language),
              towers: towers.length,
            })}
          </p>
        </div>
        <div className="min-h-0 flex-1 border-t border-line">
          <ZonesMap
            zones={zones}
            towers={towers}
            selectedId={selectedId}
            onSelect={setSelectedId}
            alerted={alerted}
            fire={fire}
            concerned={concerned}
          />
        </div>
      </Card>

      {/* On a phone, an alert in progress comes before the map. */}
      <div
        className={`flex flex-col gap-4 lg:overflow-y-auto ${alerts.length > 0 || fireIncident ? 'max-lg:order-first' : ''}`}
      >
        {fireIncident && (
          <Card title={t('residents.firesTitle')} className="border-ember">
            <FireAlertPanel
              incidents={fires}
              selectedId={fireIncident.id}
              onSelect={setChosenFire}
              proposal={proposal}
              sending={send.isPending}
              error={send.variables?.id === fireIncident.id ? (send.error?.message ?? null) : null}
              onSend={() => send.mutate({ id: fireIncident.id, confirmedBy: ALERTS.confirmedBy })}
            />
          </Card>
        )}

        <Card title={t('residents.alertsTitle')}>
          <div className="flex flex-col gap-3 px-4 pb-4">
            {alerts.length === 0 ? (
              <p className="text-ink-2">{t('residents.noAlerts')}</p>
            ) : (
              alerts.map((a) => <PhoneAlertCard key={a.id} alert={a} />)
            )}
          </div>
        </Card>

        <Card title={selected ? undefined : t('residents.title')}>
          {selected ? (
            <div className="pt-3.5">
              <ZonePanel
                zone={selected.properties}
                towers={towers.filter((tw) =>
                  selected.properties.tower_ids.includes(tw.properties.id),
                )}
                alert={zoneAlert(selected.properties.id, alerts)}
                onClose={() => setSelectedId(null)}
              />
            </div>
          ) : (
            <p className="px-4 pb-4 text-ink-2">{t('residents.pick')}</p>
          )}
        </Card>

        <Card title={t('residents.legend')}>
          <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
            <p className="eg-label">{t('residents.risk')}</p>
            <ul className="space-y-1.5">
              {LEGEND.map((l) => (
                <li key={l.key} className="flex items-center gap-2">
                  <span aria-hidden className={`size-3.5 rounded-sm border ${l.className}`} />
                  {t(`residents.riskLevel.${l.key}`)}
                </li>
              ))}
              {towers.length > 0 && (
                <li className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className="grid size-3.5 place-items-center rounded-full border border-dashed border-ink/40"
                  >
                    <span className="size-1.5 rounded-full bg-ink" />
                  </span>
                  {t('residents.tower')}
                </li>
              )}
            </ul>
            {towers.length === 0 && <p className="text-ink-2">{t('residents.towersMissing')}</p>}
            <p className="text-ink-2">{t('residents.how')}</p>
            <p className="text-ink-3">{t('residents.sources')}</p>
            <p className="text-ink-3">{t('residents.estimate')}</p>
          </div>
        </Card>
      </div>
    </div>
  )
}
