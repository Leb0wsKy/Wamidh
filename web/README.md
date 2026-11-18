# Wamidh web app (PWA)

Station dashboard, crew app, admin and resident pages in one installable, offline-capable
progressive web app. React + TypeScript (strict) + Vite, Tailwind, React Leaflet, TanStack Query,
i18next (Arabic RTL, French, English), vite-plugin-pwa.

## Run

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

The app talks to the backend (`python -m wamidh_backend`) through the Vite proxy (`/api`,
including the live WebSocket). Start the whole stack with `scripts\dev.ps1` from the repo root.
Map layers (gateways, risk overlay) come from the placement model:
`python -m placement.export_web --config config/pilot_kroumirie.yaml`.

## Pages

| Route | For | What works now |
|---|---|---|
| `/station` | fire station, big screen | one-line situation summary (sensors online, alerts, fires, radio loss, battery) with the ember alarm band and siren; map with a data tag on each sensor; sensor ledger with 60-min temperature trend and AI fire probability; **click a sensor (map or ledger) for its details**: readings as tiles (coloured only when they point to fire), location, last alert/fire, health; close with × or Escape |
| `/incidents` | fire station | list of incidents (in progress, under control) and the selected one in full: sensors, crew, access point, duration, complete audit log, Acknowledge |
| `/crew` | crew phone | choose your crew; every live fire listed (take it / taken by another crew / waiting for the station); for your missions: distance, access point, **Go**, lifecycle buttons |
| `/crew/navigate/:id` | crew phone | **Go**: in-app turn-by-turn navigation (no Google Maps, the app never hands over to another app). Driver's view: the map turns with the road, tilted, vehicle fixed at the bottom; voice instructions; reroutes after a wrong turn; route from the live GPS, else from the crew's station. Without GPS in the area, **Simulate the drive (demo ×10)** plays the route for rehearsals. Route computed offline by the backend on OSM roads |
| `/admin` | administrators | placeholder (next round) |
| `/residents` | public | placeholder (next round) |

## Checks

```bash
npm test            # vitest
npm run typecheck   # tsc, strict
npm run lint        # oxlint
npm run build       # production build + service worker
```

Types in `src/api/types.ts` mirror `contracts/api.md`; change the contract first.
