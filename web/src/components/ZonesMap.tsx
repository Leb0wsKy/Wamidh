import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import {
  Circle,
  CircleMarker,
  MapContainer,
  Marker,
  Polygon,
  Polyline,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import { useTranslation } from 'react-i18next'
import type { AlertZone, CellTower, RiskLevel } from '../api/types'
import { formatCount } from '../domain/time'
import { toLatLngs, zoneCentre, zoneLabel } from '../domain/zones'
import { iconHtml } from './iconPaths'

const FALLBACK_CENTER: [number, number] = [36.8, 8.7]

// Same palette as the rest of the interface (index.css tokens).
const RISK_FILL: Record<RiskLevel, string> = {
  high: '#b3261e',
  medium: '#e3b505',
  low: '#8a8984',
}
const INK = '#1a1a19'
const EMBER = '#b3261e'
const fireIcon = L.divIcon({
  className: '',
  html: `<div class="eg-fire-origin">${iconHtml('flame', 20)}</div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
})

/** The fire whose public alert is being prepared. */
export interface FireFocus {
  id: number
  lon: number
  lat: number
  /** radius within which zones are concerned */
  radiusM: number
}

interface Props {
  zones: AlertZone[]
  towers: CellTower[]
  selectedId: number | null
  onSelect: (zoneId: number | null) => void
  /** zones with an alert in progress */
  alerted: Set<number>
  /** the selected fire, if any, and the zones its alert would reach */
  fire?: FireFocus | null
  concerned?: Set<number>
}

function FitOnce({ zones }: { zones: AlertZone[] }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || zones.length === 0) return
    done.current = true
    const bounds = L.latLngBounds(zones.flatMap((z) => toLatLngs(z.geometry).flat(2)))
    map.fitBounds(bounds, { padding: [24, 24] })
  }, [map, zones])
  return null
}

/** Bring the selected fire into view each time another fire is selected. */
function FlyToFire({ fire }: { fire: FireFocus | null | undefined }) {
  const map = useMap()
  const shown = useRef<number | null>(null)
  useEffect(() => {
    // Wait for the radius (from the proposal) so the whole concerned area is framed.
    if (!fire || fire.radiusM <= 0 || shown.current === fire.id) return
    shown.current = fire.id
    map.flyToBounds(L.latLng(fire.lat, fire.lon).toBounds(fire.radiusM * 2.4), { duration: 0.8 })
  }, [map, fire])
  return null
}

function ClearOnMapClick({ onClear }: { onClear: () => void }) {
  useMapEvents({ click: onClear })
  return null
}

/** Inhabited zones coloured by fire risk, the cell towers that would warn them, and the
 *  links between a selected zone and its towers. */
export function ZonesMap({
  zones,
  towers,
  selectedId,
  onSelect,
  alerted,
  fire,
  concerned = new Set(),
}: Props) {
  const { t, i18n } = useTranslation()
  const towerById = useMemo(() => new Map(towers.map((tw) => [tw.properties.id, tw])), [towers])
  const shapes = useMemo(
    () => zones.map((z) => ({ zone: z, rings: toLatLngs(z.geometry) })),
    [zones],
  )
  const selected = zones.find((z) => z.properties.id === selectedId)
  const links = selected
    ? selected.properties.tower_ids.flatMap((id) => {
        const tw = towerById.get(id)
        if (!tw) return []
        const [lon, lat] = tw.geometry.coordinates
        return [{ id, line: [zoneCentre(selected.geometry), [lat, lon]] as [number, number][] }]
      })
    : []
  const serving = new Set(selected?.properties.tower_ids ?? [])

  return (
    // Same muted base map as the station; Leaflet does not support right-to-left layout.
    <div dir="ltr" className="eg-map-muted h-full w-full">
      <MapContainer
        center={FALLBACK_CENTER}
        zoom={11}
        zoomControl={false}
        className="h-full w-full"
        attributionControl
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={17}
        />
        <ZoomControl position="bottomright" />
        <FitOnce zones={zones} />
        <ClearOnMapClick onClear={() => onSelect(null)} />
        <FlyToFire fire={fire} />
        {fire && (
          <Circle
            center={[fire.lat, fire.lon]}
            radius={fire.radiusM}
            interactive={false}
            pathOptions={{ color: EMBER, weight: 1.5, dashArray: '6 6', fillOpacity: 0.04 }}
          />
        )}

        {towers.map((tw) => {
          const [lon, lat] = tw.geometry.coordinates
          const mine = serving.has(tw.properties.id)
          return (
            <Circle
              key={`cov-${tw.properties.id}`}
              center={[lat, lon]}
              radius={tw.properties.range_m}
              interactive={false}
              pathOptions={{
                stroke: mine,
                color: INK,
                weight: 1,
                dashArray: '4 4',
                fillColor: INK,
                fillOpacity: mine ? 0.06 : 0.025,
              }}
            />
          )
        })}

        {shapes.map(({ zone, rings }) => {
          const p = zone.properties
          const isSelected = p.id === selectedId
          const isAlerted = alerted.has(p.id)
          const isConcerned = concerned.has(p.id)
          return (
            <Polygon
              key={p.id}
              positions={rings}
              pathOptions={{
                color: isSelected
                  ? INK
                  : isAlerted || isConcerned
                    ? EMBER
                    : RISK_FILL[p.risk_level],
                weight: isSelected ? 3 : isAlerted || isConcerned ? 2.5 : 1,
                dashArray: isAlerted && !isSelected ? '6 4' : undefined,
                fillColor: RISK_FILL[p.risk_level],
                fillOpacity: isSelected ? 0.5 : 0.35,
                className: isAlerted ? 'eg-pulse' : undefined,
              }}
              eventHandlers={{
                click: (e) => {
                  L.DomEvent.stopPropagation(e)
                  onSelect(p.id)
                },
              }}
            >
              <Tooltip sticky>
                <span className="font-medium">{zoneLabel(p, t)}</span>
                <span className="ms-2 text-ink-2 tabular-nums">
                  {formatCount(p.population, i18n.language)}
                </span>
              </Tooltip>
            </Polygon>
          )
        })}

        {links.map((l) => (
          <Polyline
            key={`link-${l.id}`}
            positions={l.line}
            interactive={false}
            pathOptions={{ color: INK, weight: 1.5, dashArray: '2 5' }}
          />
        ))}

        {towers.map((tw) => {
          const [lon, lat] = tw.geometry.coordinates
          const mine = serving.has(tw.properties.id)
          return (
            <CircleMarker
              key={tw.properties.id}
              center={[lat, lon]}
              radius={mine ? 6 : 4}
              pathOptions={{ color: '#ffffff', weight: 1.5, fillColor: INK, fillOpacity: 1 }}
            >
              <Tooltip>
                <span dir="ltr">
                  {tw.properties.radio} · {tw.properties.id} · ~
                  {(tw.properties.range_m / 1000).toFixed(1)} km
                </span>
              </Tooltip>
            </CircleMarker>
          )
        })}
        {fire && (
          <Marker
            position={[fire.lat, fire.lon]}
            icon={fireIcon}
            interactive={false}
            zIndexOffset={1000}
          />
        )}
      </MapContainer>
    </div>
  )
}
