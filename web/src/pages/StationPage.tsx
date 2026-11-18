import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  useAlertProposal,
  useAllIncidents,
  useCrewName,
  useGateways,
  useHistory,
  useNodes,
  useOpenIncidents,
  useStations,
  useZones,
} from '../api/queries'
import { Card } from '../components/Card'
import { JournalCard } from '../components/JournalCard'
import { PopulationCard } from '../components/PopulationCard'
import { SensorLedger } from '../components/SensorLedger'
import { SituationCard } from '../components/SituationCard'
import { StationMap, type MapFocus } from '../components/StationMap'
import { WatchCard } from '../components/WatchCard'
import { DASHBOARD } from '../config'
import { dispatchOrder } from '../domain/incident'
import { ledgerRows } from '../domain/ledger'
import { useNow } from '../domain/status'
import { useDispatch } from './dispatchContext'

/**
 * Main dashboard, in boxes: the map and the sensors on the left; the situation and what needs
 * attention on the right. During a fire, the alarm band above (DispatchLayout) comes first.
 * Incidents have their own tab.
 */
export function StationPage() {
  const { t } = useTranslation()
  const { soundLocked, spread } = useDispatch()
  const nodes = useNodes().data ?? []
  const allGateways = useGateways().data ?? []
  const stations = useStations().data ?? []
  const open = dispatchOrder(useOpenIncidents().data ?? [])
  const all = useAllIncidents().data ?? []
  // 200 sensors: the list shows the ones in alarm and the highest-risk, or a search by number.
  const [query, setQuery] = useState('')
  const ledger = ledgerRows(nodes, query, DASHBOARD.ledgerRows)
  const history = useHistory(
    DASHBOARD.historyMinutes,
    DASHBOARD.historyRefreshMs,
    ledger.rows.map((n) => n.id),
  ).data
  const now = useNow()
  const crewName = useCrewName()
  // Residents near the most urgent fire; the alert itself is prepared on the Residents tab.
  const fire = open[0] ?? null
  const proposal = useAlertProposal(fire?.id ?? null).data
  const zones = useZones().data?.features ?? []
  const zonesSummary = {
    zones: zones.length,
    people: zones.reduce((sum, z) => sum + z.properties.population, 0),
    high: zones.filter((z) => z.properties.risk_level === 'high').length,
  }
  const [hovered, setHovered] = useState<number | null>(null)
  const [focus, setFocus] = useState<MapFocus | null>(null)
  // Only the gateways that serve the installed nodes.
  const used = new Set(nodes.map((n) => n.gateway_id))
  const gateways = allGateways.filter((g) => used.has(g.id))
  const trends = useMemo(
    () =>
      Object.fromEntries(
        (history?.nodes ?? []).map((n) => [n.node_id, n.points.map((p) => p.temp_c)]),
      ),
    [history],
  )
  const select = (id: number) => setFocus((f) => ({ nodeId: id, seq: (f?.seq ?? 0) + 1 }))

  return (
    <div className="h-full overflow-y-auto bg-paper">
      {/* Two independent columns, so the right-hand boxes stack without gaps. */}
      <div className="mx-auto grid max-w-[1800px] grid-cols-1 items-start gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_24rem] 2xl:grid-cols-[minmax(0,1fr)_26rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="h-[55vh] min-h-[360px] overflow-hidden">
            <StationMap
              nodes={nodes}
              gateways={gateways}
              stations={stations}
              highlightId={hovered}
              onHover={setHovered}
              focus={focus}
              now={now}
            />
          </Card>
          <Card title={t('station.sensors')} className="px-2 pb-1">
            <SensorLedger
              nodes={ledger.rows}
              total={ledger.total}
              query={query}
              onQuery={setQuery}
              now={now}
              trends={trends}
              trendMinutes={DASHBOARD.historyMinutes}
              highlightId={hovered}
              onHover={setHovered}
              onSelect={select}
            />
          </Card>
        </div>
        <div className="flex flex-col gap-4">
          <SituationCard
            incidents={open}
            nodes={nodes}
            soundLocked={soundLocked}
            spread={spread}
            now={now}
          />
          <WatchCard nodes={nodes} incidents={all} now={now} />
          <PopulationCard fire={fire} proposal={proposal} summary={zonesSummary} />
          <JournalCard incidents={all} crewName={crewName} />
        </div>
      </div>
    </div>
  )
}
