import L from 'leaflet'
import { useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Circle,
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Polygon,
  TileLayer,
  Tooltip,
  ZoomControl,
  useMap,
} from 'react-leaflet'
import type { AlertZone, Forecast, SensorNode } from '../api/types'
import { nodeStyle } from '../domain/nodeState'
import { compassPoint, type Horizon } from '../domain/spread'
import { toLatLngs } from '../domain/zones'

const EMBER = '#b3261e'
const INK = '#1a1a19'
const FALLBACK_CENTER: [number, number] = [36.79, 8.69]
// Darker where the fire is more likely to have burned by then.
const BAND_STYLE: Record<number, L.PathOptions> = {
  0.2: { fillOpacity: 0.12, weight: 1, dashArray: '4 4' },
  0.5: { fillOpacity: 0.25, weight: 1.5 },
  0.8: { fillOpacity: 0.45, weight: 2 },
}

function headIcon(deg: number): L.DivIcon {
  return L.divIcon({
    className: '',
    html: `<div class="eg-head" style="transform:rotate(${deg}deg)"><svg viewBox="0 0 24 24" width="30" height="30"><path d="M12 2 19 20 12 16 5 20Z" fill="currentColor"/></svg></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

/** Frame the forecast once per fire: the 2-hour outlook and the ignition. */
function FitToFire({ forecast }: { forecast: Forecast | undefined }) {
  const map = useMap()
  const shown = useRef<number | null>(null)
  useEffect(() => {
    if (!forecast || shown.current === forecast.incident_id) return
    shown.current = forecast.incident_id
    const layer = L.geoJSON(forecast.horizons['120'] as GeoJSON.FeatureCollection)
    const bounds = layer.getBounds()
    const ign = L.latLng(forecast.ignition.lat, forecast.ignition.lon)
    const frame = bounds.isValid() ? bounds.extend(ign) : ign.toBounds(3000)
    map.fitBounds(frame.pad(0.25), { maxZoom: 15 })
  }, [map, forecast])
  return null
}

interface Props {
  forecast: Forecast | undefined
  horizon: Horizon
  nodes: SensorNode[]
  /** population zones the forecast says are threatened */
  zones: AlertZone[]
}

export function SpreadMap({ forecast, horizon, nodes, zones }: Props) {
  const { t } = useTranslation()
  const areas = forecast?.horizons[String(horizon)]
  // Lighter bands first so the likelier ones are drawn on top.
  const data = useMemo(
    () =>
      areas
        ? ({
            type: 'FeatureCollection',
            features: [...areas.features].sort((a, b) => a.properties.p - b.properties.p),
          } as GeoJSON.FeatureCollection)
        : null,
    [areas],
  )
  const seen = new Set(forecast?.observed.map((o) => o.node_id) ?? [])
  const next = new Set(forecast?.next_nodes.map((n) => n.node_id) ?? [])
  const threatened = new Set(forecast?.threatened_zones.map((z) => z.id) ?? [])
  const bearing = forecast?.head.bearing_deg ?? null

  return (
    // Same muted base map as the station; Leaflet does not support right-to-left layout.
    <div dir="ltr" className="eg-map-muted relative h-full w-full">
      <MapContainer
        center={FALLBACK_CENTER}
        zoom={12}
        zoomSnap={0.25}
        zoomControl={false}
        className="h-full w-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={17}
        />
        <ZoomControl position="bottomright" />
        <FitToFire forecast={forecast} />

        {zones
          .filter((z) => threatened.has(z.properties.id))
          .map((z) => (
            <Polygon
              key={`zone-${z.properties.id}`}
              positions={toLatLngs(z.geometry)}
              interactive={false}
              pathOptions={{
                color: INK,
                weight: 2,
                dashArray: '5 4',
                fillColor: INK,
                fillOpacity: 0.08,
              }}
            />
          ))}

        {data && (
          <GeoJSON
            // A new layer per horizon and update: Leaflet's GeoJSON does not follow new data.
            key={`${forecast?.incident_id}-${horizon}-${forecast?.computed_at}`}
            data={data}
            interactive={false}
            style={(f) => ({
              color: EMBER,
              fillColor: EMBER,
              ...BAND_STYLE[(f?.properties as { p: number } | undefined)?.p ?? 0.5],
            })}
          />
        )}

        {nodes.map((n) => {
          const s = nodeStyle(n.state)
          const key = seen.has(n.id) || next.has(n.id)
          return (
            <CircleMarker
              key={n.id}
              center={[n.lat, n.lon]}
              radius={key ? 7 : 4}
              pathOptions={{
                color: next.has(n.id) && !seen.has(n.id) ? '#9a6400' : '#ffffff',
                weight: next.has(n.id) && !seen.has(n.id) ? 2.5 : 1.5,
                fillColor: s.color,
                fillOpacity: 1,
              }}
            >
              <Tooltip direction="top" permanent={key} offset={[0, -6]} className="eg-tag">
                {n.id}
              </Tooltip>
            </CircleMarker>
          )
        })}

        {forecast && (
          <>
            <Circle
              center={[forecast.ignition.lat, forecast.ignition.lon]}
              radius={Math.max(forecast.ignition.uncertainty_m, 30)}
              interactive={false}
              pathOptions={{ color: INK, weight: 1.5, dashArray: '3 4', fill: false }}
            />
            <CircleMarker
              center={[forecast.ignition.lat, forecast.ignition.lon]}
              radius={5}
              pathOptions={{ color: '#ffffff', weight: 2, fillColor: INK, fillOpacity: 1 }}
            >
              <Tooltip direction="bottom" offset={[0, 6]}>
                {t('spread.ignitionMark')}
              </Tooltip>
            </CircleMarker>
            {bearing !== null && (
              <Marker
                position={[forecast.ignition.lat, forecast.ignition.lon]}
                icon={headIcon(bearing)}
                interactive={false}
                zIndexOffset={1000}
              />
            )}
          </>
        )}
      </MapContainer>

      {forecast && (
        <div className="absolute top-3 left-3 z-[1000] flex items-center gap-2 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm shadow-sm">
          <svg
            aria-hidden
            viewBox="0 0 24 24"
            width={18}
            height={18}
            // The arrow shows where the wind blows TO.
            style={{ transform: `rotate(${forecast.wind.estimated_from_deg + 180}deg)` }}
            className="text-ink"
          >
            <path d="M12 3v15M6 12l6 6 6-6" fill="none" stroke="currentColor" strokeWidth={2.25} />
          </svg>
          <span className="tabular-nums">
            {t('spread.windFrom', {
              dir: t(`compass.from.${compassPoint(forecast.wind.estimated_from_deg)}`),
              kmh: Math.round(forecast.wind.estimated_speed_ms * 3.6),
            })}
          </span>
        </div>
      )}
    </div>
  )
}
