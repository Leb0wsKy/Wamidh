import L from 'leaflet'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Circle,
  LayerGroup,
  LayersControl,
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import type { Gateway, NodeState, SensorNode, Station } from '../api/types'
import { bySeverity, nodeStyle } from '../domain/nodeState'
import { bearingLabel, distanceKm } from '../domain/navigation'
import { Icon } from './Icon'
import { nodeIcon, setHighlight } from './mapIcons'
import { SensorDetails } from './SensorDetails'
import { iconHtml } from './iconPaths'

const FALLBACK_CENTER: [number, number] = [36.765, 8.65]
const gatewayIcon = L.divIcon({
  className: '',
  html: `<div class="eg-gateway">${iconHtml('gateway', 20)}</div>`,
  iconSize: [20, 20],
  iconAnchor: [10, 18],
})
const stationIcon = L.divIcon({
  className: '',
  html: `<div class="eg-station">${iconHtml('truck', 20)}</div>`,
  iconSize: [32, 32],
  iconAnchor: [16, 16],
})

// Below this zoom the sensors crowd together: only sensors in alert, on fire or silent keep
// their data tag (and the one under the pointer); healthy ones show just their number.
const MIN_ZOOM_CALM_TAGS = 13
// Below this zoom healthy sensors are small dots without their number: with 200 sensors the
// numbered discs would cover each other. Sensors in alarm keep the full marker at every zoom.
const MIN_ZOOM_NUMBERS = 12

/** Worse states are drawn on top. */
const Z_BY_STATE: Record<NodeState, number> = {
  FIRE: 1000,
  LOST_PROBABLY_BURNED: 800,
  ALERT: 600,
  OFFLINE: 400,
  NORMAL: 0,
}

/** A request to centre the map on a sensor; `seq` makes repeated clicks on one card work. */
export interface MapFocus {
  nodeId: number
  seq: number
}

interface Props {
  nodes: SensorNode[]
  gateways: Gateway[]
  stations: Station[]
  /** sensor under the pointer in the card list */
  highlightId?: number | null
  onHover?: (nodeId: number | null) => void
  focus?: MapFocus | null
  /** current time, for "last contact" and history in the popup */
  now: number
}

const FIT: L.FitBoundsOptions = {
  paddingTopLeft: [40, 70],
  paddingBottomRight: [40, 40],
  maxZoom: 14,
}

/** Frame the nodes once, when they are first known. */
function FitOnce({ points }: { points: [number, number][] }) {
  const map = useMap()
  const done = useRef(false)
  useEffect(() => {
    if (done.current || points.length === 0) return
    map.fitBounds(L.latLngBounds(points), FIT)
    done.current = true
  }, [map, points])
  return null
}

/** Report the zoom level, so calm data tags can hide when sensors crowd together. */
function ZoomWatch({ onZoom }: { onZoom: (z: number) => void }) {
  const map = useMapEvents({ zoomend: () => onZoom(map.getZoom()) })
  useEffect(() => onZoom(map.getZoom()), [map, onZoom])
  return null
}

/** Fly to a sensor asked for from the ledger, then open its popup. */
function FocusOn({
  focus,
  nodes,
  open,
}: {
  focus: MapFocus | null
  nodes: SensorNode[]
  open: (nodeId: number) => void
}) {
  const map = useMap()
  const handled = useRef(0)
  useEffect(() => {
    if (!focus || focus.seq === handled.current) return
    const n = nodes.find((x) => x.id === focus.nodeId)
    if (!n) return
    handled.current = focus.seq
    map.flyTo([n.lat, n.lon], Math.max(map.getZoom(), 14), { duration: 0.6 })
    map.once('moveend', () => open(n.id))
  }, [map, focus, nodes, open])
  return null
}

export function StationMap({
  nodes,
  gateways,
  stations,
  highlightId = null,
  onHover,
  focus = null,
  now,
}: Props) {
  const { t } = useTranslation()
  // Draw healthy nodes first so alerts and fires sit on top.
  const ordered = [...nodes].sort((a, b) => bySeverity(b.state, a.state))
  const [map, setMap] = useState<L.Map | null>(null)
  // Dev builds only: lets the end-to-end check read the map.
  useEffect(() => {
    if (import.meta.env.DEV && map)
      (window as unknown as { egStationMap?: L.Map }).egStationMap = map
  }, [map])
  const [zoom, setZoom] = useState(12)
  const markers = useRef(new Map<number, L.Marker>())
  // Highlight by marking the marker element in place (see mapIcons.ts).
  useEffect(() => {
    for (const [id, m] of markers.current) setHighlight(m.getElement(), id === highlightId)
  }, [highlightId, nodes])
  const openPopup = useCallback((id: number) => markers.current.get(id)?.openPopup(), [])
  // Escape closes the open sensor popup, wherever the keyboard focus is.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') map?.closePopup()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [map])
  const nodePoints = nodes.map((n): [number, number] => [n.lat, n.lon])
  const centre = nodes.length
    ? {
        lat: nodes.reduce((a, n) => a + n.lat, 0) / nodes.length,
        lon: nodes.reduce((a, n) => a + n.lon, 0) / nodes.length,
      }
    : null

  return (
    // Leaflet does not support right-to-left layout; the map stays LTR in every language.
    <div dir="ltr" className="eg-map-muted relative h-full w-full">
      <MapContainer
        center={FALLBACK_CENTER}
        zoom={12}
        // Quarter steps: the 200 sensors span ~50 km, and whole steps would leave the
        // installation small in the middle of the map.
        zoomSnap={0.25}
        zoomDelta={0.5}
        zoomControl={false}
        className="h-full w-full"
        ref={setMap}
      >
        <FitOnce points={nodePoints} />
        <FocusOn focus={focus} nodes={nodes} open={openPopup} />
        <ZoomWatch onZoom={setZoom} />
        <ZoomControl position="bottomright" />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={17}
        />
        <LayersControl position="topright">
          <LayersControl.Overlay
            checked
            name={t('station.coverageZone', { r: nodes[0]?.coverage_radius_m ?? 500 })}
          >
            <LayerGroup>
              {ordered.map((n) => {
                const s = nodeStyle(n.state)
                const calm = n.state === 'NORMAL'
                return (
                  <Circle
                    key={`zone-${n.id}-${n.state}`}
                    center={[n.lat, n.lon]}
                    radius={n.coverage_radius_m ?? 500}
                    interactive={false}
                    pathOptions={{
                      color: s.color,
                      weight: calm ? 1 : 2,
                      opacity: calm ? 0.55 : 0.9,
                      fillColor: s.color,
                      fillOpacity: n.state === 'FIRE' ? 0.22 : calm ? 0.06 : 0.14,
                      className: s.pulse ? 'eg-pulse' : undefined,
                    }}
                  />
                )
              })}
            </LayerGroup>
          </LayersControl.Overlay>
          <LayersControl.Overlay checked name={t('station.gateways')}>
            <LayerGroup>
              {gateways.map((g) => (
                <Marker key={g.id} position={[g.lat, g.lon]} icon={gatewayIcon}>
                  <Tooltip>
                    {t('station.gateways')} {g.id} · {Math.round(g.elevation_m)} m
                  </Tooltip>
                </Marker>
              ))}
            </LayerGroup>
          </LayersControl.Overlay>
          <LayersControl.Overlay checked name={t('station.nodes')}>
            <LayerGroup>
              {ordered.map((n) => (
                <Marker
                  // A stable key: the marker is updated in place, never remounted, so an open
                  // popup stays open while live readings arrive.
                  key={n.id}
                  ref={(m) => {
                    if (m) markers.current.set(n.id, m)
                    else markers.current.delete(n.id)
                  }}
                  position={[n.lat, n.lon]}
                  icon={nodeIcon(n.id, n.state, n.state === 'NORMAL' && zoom < MIN_ZOOM_NUMBERS)}
                  zIndexOffset={n.id === highlightId ? 2000 : Z_BY_STATE[n.state]}
                  title={`${t('station.node')} ${n.id} · ${t(nodeStyle(n.state).labelKey)}`}
                  eventHandlers={{
                    mouseover: () => onHover?.(n.id),
                    mouseout: () => onHover?.(null),
                  }}
                >
                  {/* Data tag, like the labels beside aircraft on a radar screen: the sensor's
                      number, temperature and on-board fire estimate, readable on the map. */}
                  {(n.state !== 'NORMAL' || zoom >= MIN_ZOOM_CALM_TAGS || n.id === highlightId) && (
                    <Tooltip
                      permanent
                      direction="right"
                      offset={[n.state === 'FIRE' ? 16 : 13, 0]}
                      className={`eg-tag eg-tag-${n.state}`}
                    >
                      <span className="eg-tag-id">{n.id}</span>
                      {n.state === 'OFFLINE' || n.state === 'LOST_PROBABLY_BURNED' ? (
                        <span>{t(nodeStyle(n.state).labelKey)}</span>
                      ) : (
                        <span className="tabular-nums">
                          {n.readings?.temp_c != null ? `${n.readings.temp_c.toFixed(1)} °C` : '—'}
                          {n.readings?.fire_prob != null &&
                            ` · ${Math.round(n.readings.fire_prob * 100)} %`}
                        </span>
                      )}
                    </Tooltip>
                  )}
                  <Popup
                    closeButton={false}
                    autoPanPadding={[24, 24]}
                    className="eg-popup"
                    maxWidth={320}
                  >
                    <SensorDetails node={n} now={now} onClose={() => map?.closePopup()} />
                  </Popup>
                </Marker>
              ))}
            </LayerGroup>
          </LayersControl.Overlay>
        </LayersControl>
        {stations.map((s) => (
          <Marker key={s.id} position={[s.lat, s.lon]} icon={stationIcon}>
            <Tooltip permanent direction="right" offset={[18, 0]} className="eg-station-label">
              {s.name.split(' — ').at(-1)}
            </Tooltip>
          </Marker>
        ))}
      </MapContainer>

      {/* The station may be off screen, so it is always named, with its distance. */}
      {centre && stations.length > 0 && (
        <div className="absolute top-3 left-3 z-[1000] flex items-stretch overflow-hidden rounded-md border border-line-strong bg-surface text-sm shadow-sm">
          {stations.map((s) => (
            <button
              key={s.id}
              type="button"
              title={s.name}
              onClick={() => map?.fitBounds(L.latLngBounds([...nodePoints, [s.lat, s.lon]]), FIT)}
              className="flex items-center gap-1.5 border-e border-line px-2.5 py-1.5 hover:bg-paper"
            >
              <Icon name="truck" size={16} className="text-ember" />
              {/* "Protection civile — Aïn Draham": the town is what tells them apart. */}
              <span className="font-medium text-ink">{s.name.split(' — ').at(-1)}</span>
              <span className="text-ink-2 tabular-nums">
                {distanceKm(centre, s).toFixed(0)} km {bearingLabel(centre, s)}
              </span>
            </button>
          ))}
          <button
            type="button"
            title={t('station.centerNodes')}
            aria-label={t('station.centerNodes')}
            onClick={() => map?.fitBounds(L.latLngBounds(nodePoints), FIT)}
            className="grid place-items-center px-2.5 text-ink-2 hover:bg-paper hover:text-ink"
          >
            <Icon name="locate" size={18} />
          </button>
        </div>
      )}
    </div>
  )
}
