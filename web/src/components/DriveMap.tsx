// Driver's-view map for the navigation screen: the map turns so the road ahead points up,
// tilted like a windscreen view, with the vehicle fixed in the lower part of the screen.
// MapLibre GL (not Leaflet) because Leaflet cannot rotate the map. Same OSM raster tiles,
// so the PWA tile cache still applies.

import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type { LonLat, NavRoute } from '../api/types'
import { iconHtml } from './iconPaths'

const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}
const DRIVE_ZOOM = 17
const DRIVE_PITCH = 60
/** share of the map height kept above the vehicle, so the road ahead fills the screen */
const AHEAD_SHARE = 0.5
const BLUE = '#2a78d6'

type Coords = [number, number][]

function line(coords: Coords): GeoJSON.Feature<GeoJSON.LineString> {
  return { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }
}

function element(html: string): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = html
  return el
}

interface Props {
  route: NavRoute
  /** road still to drive, [lon, lat] */
  ahead: Coords
  position: LonLat | null
  /** direction of travel, degrees clockwise from north */
  heading: number
  follow: boolean
  /** time between position updates; the camera glides for that long, so it never lags */
  updateMs: number
  onUserMove: () => void
}

export function DriveMap({ route, ahead, position, heading, follow, updateMs, onUserMove }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const me = useRef<maplibregl.Marker | null>(null)
  const extras = useRef<maplibregl.Marker[]>([])
  const ready = useRef(false)
  const onMove = useRef(onUserMove)
  useEffect(() => {
    onMove.current = onUserMove
  }, [onUserMove])

  useEffect(() => {
    if (!box.current) return
    const m = new maplibregl.Map({
      container: box.current,
      style: STYLE,
      center: [8.69, 36.79], // Kroumirie; the overview below fits the route at once
      zoom: 13,
      attributionControl: { compact: true },
    })
    map.current = m
    // Dev builds only: lets the end-to-end check read the camera.
    if (import.meta.env.DEV) (window as unknown as { egMap?: maplibregl.Map }).egMap = m
    const user = (e: { originalEvent?: unknown }) => {
      if (e.originalEvent) onMove.current() // ignore moves made by the code itself
    }
    m.on('dragstart', user)
    m.on('rotatestart', user)
    m.on('pitchstart', user)
    m.on('load', () => {
      m.addSource('ahead', { type: 'geojson', data: line([]) })
      m.addSource('walk', { type: 'geojson', data: line([]) })
      const round = { 'line-cap': 'round', 'line-join': 'round' } as const
      m.addLayer({
        id: 'ahead-casing',
        type: 'line',
        source: 'ahead',
        layout: round,
        paint: { 'line-color': '#fff', 'line-width': 13 },
      })
      m.addLayer({
        id: 'ahead',
        type: 'line',
        source: 'ahead',
        layout: round,
        paint: { 'line-color': BLUE, 'line-width': 8 },
      })
      m.addLayer({
        id: 'walk',
        type: 'line',
        source: 'walk',
        layout: round,
        paint: { 'line-color': '#1a1a19', 'line-width': 4, 'line-dasharray': [0.2, 2.5] },
      })
      ready.current = true
      m.fire('eg:ready')
    })
    me.current = new maplibregl.Marker({
      element: element(
        `<svg width="44" height="44" viewBox="0 0 44 44" aria-hidden="true">
           <circle cx="22" cy="22" r="20" fill="${BLUE}" stroke="#fff" stroke-width="4"/>
           <path d="M22 9 L32 32 L22 26 L12 32 Z" fill="#fff"/>
         </svg>`,
      ),
      rotationAlignment: 'map',
      pitchAlignment: 'map',
    })
    return () => {
      ready.current = false
      m.remove()
      map.current = null
    }
  }, [])

  // Route lines and fixed markers (fire, access point, station).
  useEffect(() => {
    const m = map.current
    if (!m) return
    const draw = () => {
      ;(m.getSource('ahead') as maplibregl.GeoJSONSource | undefined)?.setData(line(ahead))
      ;(m.getSource('walk') as maplibregl.GeoJSONSource | undefined)?.setData(
        line(route.walk.geometry),
      )
    }
    if (ready.current) draw()
    else m.once('eg:ready', draw)
  }, [route, ahead])

  useEffect(() => {
    const m = map.current
    if (!m) return
    for (const x of extras.current) x.remove()
    const access = route.walk.geometry[0]!
    extras.current = [
      new maplibregl.Marker({
        element: element(
          '<div style="width:16px;height:16px;border-radius:50%;background:#fff;border:3px solid #1a1a19"></div>',
        ),
      }).setLngLat(access),
      new maplibregl.Marker({
        element: element(
          `<div style="display:grid;place-items:center;width:36px;height:36px;border-radius:50%;background:#b3261e;color:#fff;border:3px solid #fff;box-shadow:0 1px 4px #0005">${iconHtml('flame', 20, true)}</div>`,
        ),
      }).setLngLat([route.target.lon, route.target.lat]),
      ...(route.origin.source === 'station'
        ? [
            new maplibregl.Marker({
              element: element(`<div class="eg-station">${iconHtml('truck', 20)}</div>`),
            }).setLngLat([route.origin.lon, route.origin.lat]),
          ]
        : []),
    ]
    for (const x of extras.current) x.addTo(m)
  }, [route])

  // Overview before the vehicle moves: the whole route, north up, flat.
  useEffect(() => {
    const m = map.current
    if (!m || position) return
    const all = [...route.drive.geometry, ...route.walk.geometry]
    const bounds = all.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(all[0]!, all[0]!))
    m.fitBounds(bounds, { padding: 50, bearing: 0, pitch: 0, duration: 0 })
  }, [route, position])

  // Driving: the vehicle stays put near the bottom, the map turns and moves under it.
  const lastFix = useRef(0)
  useEffect(() => {
    const m = map.current
    const marker = me.current
    if (!m || !marker) return
    if (!position) {
      marker.remove()
      return
    }
    marker.setLngLat([position.lon, position.lat]).addTo(m)
    // Following: the arrow is fixed pointing up the screen. Panned away: it shows the heading.
    marker.setRotationAlignment(follow ? 'viewport' : 'map').setRotation(follow ? 0 : heading)
    if (!follow) return
    const now = performance.now()
    const gap = lastFix.current ? now - lastFix.current : updateMs
    lastFix.current = now
    const h = m.getContainer().clientHeight
    const camera = {
      center: [position.lon, position.lat] as [number, number],
      bearing: heading,
      pitch: DRIVE_PITCH,
      zoom: Math.max(m.getZoom(), DRIVE_ZOOM),
      padding: { top: h * AHEAD_SHARE, bottom: 0, left: 0, right: 0 },
    }
    const entering = m.getPitch() < DRIVE_PITCH - 5 || m.getZoom() < DRIVE_ZOOM - 0.5
    if (entering) {
      m.jumpTo(camera)
    } else {
      // Glide until the next fix is due, so each move ends before the next one starts.
      m.easeTo({ ...camera, duration: Math.min(gap, 2 * updateMs) * 0.9, easing: (t) => t })
    }
  }, [position, heading, follow, updateMs])

  return <div ref={box} className="h-full w-full" />
}
