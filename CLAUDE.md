# CLAUDE.md — Wamidh

> The project is named **Wamidh** (it replaced the placeholder "EmberGuard", see ADR 0005). Python packages are `wamidh_*`, MQTT topics start with `wamidh/v1/`, environment variables with `WAMIDH_`.

## 1. What we are building

Wamidh is our entry for the **IEEE TSYP14 NEXUS Technical Challenge** (Environmental & Climate Sensing track): a low-cost, solar-powered network that detects forest fires in Tunisia in their first minutes and delivers an actionable alert to firefighters.

End-to-end chain (the challenge's "Detect → Communicate → Coordinate → Enable Response"):

1. **Plan** — an AI placement model finds where fires start (95% are human-caused, near roads/farms/villages) and chooses where to put a limited number of nodes.
2. **Sense** — ESP32 nodes (infrared flame + BME688 gas/temp/humidity) run a TinyML classifier on-board. *(Firmware is out of scope for now.)*
3. **Communicate** — nodes → gateway (ESP-NOW in prototype, LoRa in the field) → MQTT → backend.
4. **Coordinate** — backend runs node state tracking, offline detection, alert lifecycle, escalation, and the fire spread prediction engine.
5. **Respond** — station siren + dashboard; crews use a PWA with a **Go** button that routes them to the nearest vehicle access point; residents in the threatened zones receive an Arabic Cell Broadcast alert confirmed by the dispatcher (ADR 0003 supersedes the opt-in SMS described below).

### Current scope (this phase)

| Component | Status | Priority |
|---|---|---|
| `placement/` — AI node placement model | **Build now** | **P0** (its figures and metrics go into the report due 12 Oct 2026) |
| `spread/` — fire spread prediction engine | Build now | P1 |
| `backend/` + `web/` — PWA, API, database | Build now | P1 |
| `simulator/` — virtual nodes publishing MQTT | Build now (replaces hardware until IoT is ready) | P1 |
| `firmware/` — ESP32 nodes, gateway, station receiver | **Later — do not start** | P2 |

## 2. Deadlines and how we are graded

- **12 Oct 2026** — Phase 1 report (PDF, ≤30 pages, anonymous). The placement model must produce figures and metrics before then.
- **10 Dec 2026** — Phase 2: live presentation, working prototype, **GitHub repository**, recorded or live demo, circuit/system diagrams.

Phase 2 scoring (50 pts) and what it means for code:

| Criterion | Pts | What earns it in this repo |
|---|---|---|
| Prototype demonstration | 15 | A flawless 2-minute demo: simulated fire → siren → dashboard → Go → spread prediction. Rehearsable with one command. |
| Feasibility & real-world deployment | 10 | Real Tunisian data, realistic constraints (offline, low bandwidth, heat), measured numbers, not claims. |
| Presentation | 8 | Clean screenshots, report-ready figures, consistent visual identity. |
| Sustainability demonstration | 7 | Power-aware design surfaced in the UI (battery levels, reporting intervals), maintenance workflows. |
| GitHub repository | 5 | Clear README, one-command setup, tests, CI badge, architecture diagram, docs. |
| Community & SDG impact narrative | 5 | Resident opt-in, Arabic/French UI, risk maps shareable with municipalities. |

Phase 1 technical soundness (15 pts) rewards: innovation & efficiency, system architecture, ethics & technology, technical feasibility, **use of the right methodologies and tools**. Always document *why* a method was chosen (see `docs/adr/`).

### Hard rules from the challenge

- **Anonymity.** No team member names, school, university or IEEE Student Branch anywhere: code, comments, commits, README, screenshots, metadata, file paths. Before the first commit, the team configures a neutral git identity for this repo (`git config user.name "Wamidh Team"`, a neutral email). Never write personal names into files.
- **Not a pure software project.** Every software feature must visibly connect to sensing. The simulator must use the *same* message contract as future firmware.

## 3. Repository layout

```
wamidh/
├── CLAUDE.md
├── README.md                 # Judges read this first: pitch, diagram, quickstart, screenshots, results
├── docker-compose.yml        # postgres+postgis, mosquitto, backend, web (and optional simulator)
├── .env.example
├── .github/workflows/ci.yml  # lint + tests for Python and web
├── contracts/                # Single source of truth shared by all components
│   ├── mqtt_topics.md
│   ├── telemetry.schema.json
│   └── packet_format.md      # 19-byte binary layout for LoRa (see §5)
├── placement/                # P0 — AI node placement
├── spread/                   # P1 — fire spread prediction engine (Python package)
├── backend/                  # FastAPI app
├── web/                      # React PWA
├── simulator/                # Virtual nodes + scenarios
├── firmware/                 # Later. Keep only a README placeholder for now.
└── docs/
    ├── architecture.md       # Mermaid diagrams
    ├── adr/                  # Architecture Decision Records (0001-use-fastapi.md, ...)
    ├── demo-script.md        # Minute-by-minute Phase 2 demo
    └── figures/              # Report-ready exports (PNG 300 dpi + SVG)
```

## 4. Conventions

- **Python 3.11+**, `uv` or `pip` + `pyproject.toml` per package. Format with `ruff format`, lint with `ruff`. Type hints everywhere; `mypy --strict` on `spread/` and `backend/`.
- **Web:** TypeScript strict, ESLint + Prettier.
- **Tests:** `pytest` (Python), `vitest` (web), one Playwright end-to-end test for the full alert flow.
- **Commits:** Conventional Commits (`feat(placement): add greedy max-coverage optimiser`).
- **Config:** YAML files under each package's `config/`, never hard-coded constants for thresholds, radii, intervals.
- **Reproducibility:** fixed random seeds, pinned dependencies, data download scripts instead of committed raw data. Large data goes in `data/` (git-ignored) with a `data/README.md` explaining how to fetch it.
- **Coordinates:** store WGS84 (EPSG:4326); compute distances and areas in **EPSG:32632** (UTM zone 32N, covers northern Tunisia).
- **Units:** SI, metres, minutes for spread, seconds for timestamps (UTC in storage, Africa/Tunis in the UI).
- **Visual identity:** accent `#B3261E`, soft `#F4E9E7`. All matplotlib figures use one shared style file (`docs/figures/wamidh.mplstyle`) and export PNG at 300 dpi and SVG.
- **Honesty:** never invent data or results. If a number is an assumption, label it as one in code comments, config, and output.

## 5. Shared contracts (implement first, everything depends on them)

### Node states and reporting (field configuration)

| State | Trigger | Reporting interval | Declared offline after |
|---|---|---|---|
| `NORMAL` | Readings within local baseline | 15 min | 60 min of silence |
| `ALERT` | Anomalous readings, fire not confirmed | 2 min | 10 min of silence |
| `FIRE` | Classifier confirms fire | Immediately, then continuous | 5 min of silence → `LOST_PROBABLY_BURNED` |

- The **prototype** reports every 2 min in all states; intervals are config values.
- A node silent while in `FIRE` is **not a fault**: mark it `LOST_PROBABLY_BURNED` and feed that event to the spread engine as evidence that the fire reached it.
- Offline from `NORMAL`/`ALERT` → `OFFLINE` (maintenance ticket).

### MQTT topics

```
wamidh/v1/nodes/{node_id}/telemetry   # periodic readings (QoS 1)
wamidh/v1/nodes/{node_id}/event       # state transitions, fire alerts (QoS 1)
wamidh/v1/stations/{station_id}/cmd   # siren on/off, sent by backend to station receivers
wamidh/v1/stations/{station_id}/ack   # acknowledgement button
```

### Telemetry JSON (mirrors the 19-byte binary packet)

```json
{
  "node_id": 42,
  "seq": 1024,
  "ts": "2026-10-01T12:00:00Z",
  "state": "ALERT",
  "gas_ratio": 0.62,
  "temp_c": 41.3,
  "rh_pct": 12.0,
  "flame": false,
  "fire_prob": 0.71,
  "battery_v": 3.28,
  "sig": "base64-hmac"
}
```

- `gas_ratio` = current gas resistance ÷ node's local baseline (smoke lowers resistance, so ratio < 1).
- `sig` = truncated HMAC over the payload with a per-node key. The backend **rejects** unsigned or invalid messages (ethics & security point: no injected false alerts).
- `seq` lets the backend detect lost packets; show packet loss per node in the admin view.

## 6. `placement/` — AI node placement (P0)

**Goal:** an ignition-susceptibility map for northern Tunisia, then an optimised set of node (and gateway) locations for the Kroumirie pilot zone (Jendouba governorate), with report-ready figures and metrics.

### 6.1 Data sources (verify dataset IDs before use)

| Layer | Source | Notes |
|---|---|---|
| Fire history | NASA FIRMS archive download for Tunisia: VIIRS 375 m (2012–2025) + MODIS 1 km (2001–2025) | Download CSV/SHP from the FIRMS archive. Keep `confidence`, `frp`, `acq_date`, `daynight`. |
| Elevation, slope, aspect | SRTM 30 m (GEE `USGS/SRTMGL1_003`) | Derive slope/aspect in GEE (`ee.Terrain`). |
| Land cover | ESA WorldCover 10 m (GEE `ESA/WorldCover/v200`) | Tree cover, shrubland, grassland, cropland classes. |
| Vegetation | Sentinel-2 NDVI summer median (GEE `COPERNICUS/S2_SR_HARMONIZED`) | Cloud-masked June–August composite. |
| Climate | ERA5-Land (GEE `ECMWF/ERA5_LAND/DAILY_AGGR`) | Summer mean max temperature, precipitation, wind speed. |
| Human activity | OpenStreetMap Tunisia extract (Geofabrik) or `osmnx` | Distance to roads, tracks, settlements; also used for access points. |
| Admin boundaries | GADM or geoBoundaries | Governorates for the spatial split. |

### 6.2 Pipeline (one script per step, orchestrated by `make` or a `pipeline.py`)

1. `01_download.py` — FIRMS CSV, OSM extract, boundaries. Earth Engine export scripts for rasters (to Google Drive, then local).
2. `02_clean_fires.py`
   - Keep summer season (May–October), confidence ≥ nominal, drop low-FRP noise.
   - **Remove detections on cropland** (WorldCover class) to exclude agricultural burning.
   - Deduplicate same-fire clusters (DBSCAN in space and time) so one large fire does not dominate.
3. `03_grid.py` — 375 m grid aligned with VIIRS over forest/shrub mask of northern Tunisia.
4. `04_features.py` — per cell: elevation, slope, aspect (sin/cos), land cover fractions, NDVI, distance to road / track / settlement / cropland edge, climate normals.
5. `05_labels.py` — positive = cell with ≥1 cleaned detection; negatives sampled from forest cells without detections (balanced, stratified by governorate). Document the sampling.
6. `06_train.py`
   - Models: logistic regression (baseline), Random Forest, XGBoost/LightGBM.
   - **Spatial cross-validation** (hold out whole governorates or spatial blocks). Random splits leak spatial autocorrelation and inflate scores; say so in the report.
   - Metrics: ROC-AUC, PR-AUC, precision/recall at chosen threshold, calibration curve. Calibrate probabilities (isotonic) so the optimiser gets real probabilities.
   - Explainability: permutation importance + **SHAP** summary plot. Expect distance to roads/settlements to rank high; if it does, it validates the "95% human-caused" story.
7. `07_predict.py` — susceptibility GeoTIFF for the whole study area + pilot zone.
8. `08_optimise.py` — node placement:
   - Candidates: cells within walking distance (config, e.g. ≤ 300 m) of an OSM track or road, so nodes are maintainable.
   - Greedy **maximum coverage**: repeatedly add the candidate covering the most uncovered risk within detection radius `r` (default 60 m, config). Guarantee: ≥ 63% (1 − 1/e) of optimum.
   - **Wind-aware coverage (creative, cheap):** weight coverage toward the upwind side using the dominant summer wind direction from ERA5, because smoke travels downwind to the node.
   - **Gateway placement:** compute DEM **viewsheds** from high points; choose the fewest gateways such that every node has line of sight to at least one gateway (set cover). This proves radio feasibility.
   - Output: `nodes.geojson`, `gateways.geojson`, and the coverage-vs-N curve.
9. `09_figures.py` — all report figures (see 6.3).

### 6.3 Figures and numbers the report needs (by 12 Oct)

- `fig_firms_map` — cleaned fire detections over northern Tunisia.
- `fig_risk_map_pilot` — susceptibility map of Kroumirie with selected nodes and gateways.
- `fig_coverage_curve` — share of total risk covered vs number of nodes (mark 50, 100, 200 nodes).
- `fig_shap` — feature importance.
- `metrics.json` — AUC, PR-AUC, precision/recall, top features, % risk covered by 200 nodes, number of gateways, share of the pilot zone's high-risk area within X m of roads (supports the market-size estimate).

### 6.4 Done when

`python -m placement.pipeline --config config/pilot_kroumirie.yaml` runs end to end from downloaded data, produces all figures and `metrics.json`, and tests cover the optimiser (known toy grid → known optimal answer).

## 7. `spread/` — fire spread prediction engine (P1)

A physics-based model corrected by live observations. Present it as a **prediction engine** combining a minimum-travel-time model with Bayesian data assimilation from node alerts.

### 7.1 Core model

- **Grid** over the pilot zone at 50–100 m (config), reusing placement layers (DEM, land cover, NDVI).
- **Fuel classes** from WorldCover → base rate of spread (m/min) in `config/fuels.yaml`. Values are **assumptions** from the literature; label them.
- **Slope effect:** rate of spread roughly doubles for every 10° upslope (factor ≈ exp(0.069 · slope°)), reduced downslope.
- **Wind effect:** elliptical spread with length-to-breadth ratio from wind speed (Anderson 1983 relation). Directional rate of spread for each of 16 neighbour directions.
- **Minimum travel time:** arrival time from the ignition point via Dijkstra on a **16-neighbour** grid (reduces the diamond-shaped artefacts of 8-neighbour grids), following Finney (2002).
- Must run in **under 2 s** for a 20 × 20 km zone at 100 m. Use `numpy` + `scipy.sparse.csgraph.dijkstra` or `numba`.

### 7.2 Learning from alerts (the "AI" part)

- **Ensemble:** run N = 100–200 simulations with perturbed wind direction/speed, fuel rate multipliers and ignition location (the fire started upwind of the first detecting node, within its radius).
- **Particle filter:** each time a node reports `FIRE` or `LOST_PROBABLY_BURNED`, weight each ensemble member by how well its predicted arrival time at that node matches the observed time; resample.
- **Negative evidence:** a node still `NORMAL` when a member says the fire should have reached it lowers that member's weight.
- **Output:** probability that each cell burns within 15 / 30 / 60 / 120 min; estimated ignition point; estimated current front. Exposed as GeoJSON contours and a PNG overlay.

### 7.3 Firebreak suggestion (creative, advisory only)

- Represent the grid as a flow network from the fire front to a protected asset (village polygon from OSM).
- Compute a **minimum cut** weighted by the effort of clearing each cell: the cheapest line of cells that separates the fire from the village, restricted to cells the fire will not reach before crews can (arrival time > estimated crew arrival + work time).
- Show it as a dashed line labelled "Suggested firebreak (advisory)". The UI must state that decisions stay with the crews.

### 7.4 Validation

- **Synthetic:** known ignition + known parameters → recover them from simulated node alerts.
- **Historical backtest:** 2–3 documented Tunisian fires (e.g. Melloula, July 2023) using burned-area polygons (EFFIS or MODIS MCD64A1). Compare predicted vs actual burned area (Jaccard / Sørensen index). Report honestly even if modest.

### 7.5 API

```python
engine = SpreadEngine.from_config("config/pilot_kroumirie.yaml")
run = engine.start(ignition_hint=(lat, lon), t0=..., weather=...)
run.observe(node_id=12, event="FIRE", t=...)
forecast = run.forecast(horizons_min=[15, 30, 60, 120])   # GeoJSON + summary
breaks = run.suggest_firebreaks(asset="village:melloula")
```

The backend imports this package directly (same process) — no separate service.

## 8. `backend/` — FastAPI (P1)

### Stack

FastAPI · SQLAlchemy 2 + Alembic · **PostgreSQL + PostGIS** · `aiomqtt` for ingest · WebSockets for live updates · APScheduler (or an asyncio loop) for watchdogs · `pywebpush` for Web Push · JWT auth with roles.

### Data model (minimum)

- `node(id, location geography, zone_id, install_date, state, last_seen, battery_v, hmac_key_ref, firmware_version)`
- `telemetry(node_id, ts, seq, state, gas_ratio, temp_c, rh_pct, flame, fire_prob, battery_v)` — index on `(node_id, ts)`.
- `station(id, name, location, zone_ids[], contact)`
- `access_point(id, location, road_type, source)` — precomputed from OSM: where a vehicle road/track is closest to forest.
- `incident(id, status, first_node_id, estimated_origin, created_at, acknowledged_at, acknowledged_by, closed_at)`
- `incident_event(incident_id, ts, type, payload)` — full **audit log** (transparency).
- `crew(id, station_id, name_alias)`, `dispatch(incident_id, crew_id, status, timestamps)`
- `resident_subscription(id, phone_hash, phone_encrypted, zone_id, language, consent_at, revoked_at)` — consent recorded, revocable, no other personal data.
- `user(id, role: dispatcher|crew|admin, station_id)`

### Core services

1. **Ingest:** subscribe to MQTT, verify HMAC, deduplicate by `seq`, write telemetry, run the node state machine.
2. **Watchdog:** every 30 s, apply offline thresholds from §5; emit `OFFLINE` or `LOST_PROBABLY_BURNED`.
3. **Incident manager:**
   - First `FIRE` event in a zone → create incident; attach later `FIRE` events within X km / Y min to the same incident.
   - Lifecycle: `NEW → STATION_NOTIFIED → ACKNOWLEDGED → EN_ROUTE → ON_SITE → UNDER_CONTROL → CLOSED` (+ `FALSE_ALARM`).
   - Notify station (MQTT siren command + Web Push + WebSocket).
   - **Escalation:** not acknowledged in 3 min (config) → next nearest station + regional Civil Protection.
4. **Spread service:** on each incident event, call the spread engine and push the updated forecast.
5. **Routing service (provider abstraction):** OpenRouteService or OSRM/GraphHopper behind an interface. Returns route to the **nearest access point** to the estimated fire zone, plus the final off-road segment along OSM tracks. Mock provider for tests and offline demos.
6. **SMS service (provider abstraction)** — *superseded by ADR 0003: Cell Broadcast to alert zones (`zones/`, `alerts.py`, `broadcast.py`), no opt-in, no phone numbers stored.* `ConsoleSMSProvider` (prints/logs, used in demo) + one real provider adapter. Only **confirmed** incidents trigger resident SMS. Templates in Tunisian Arabic and French.
7. **Estimated fire zone:** the fire lies **upwind** of the detecting node: return an ellipse upwind of the node sized by detection radius and time since alert. Upgraded to the spread forecast when available.

### API (REST under `/api/v1`, OpenAPI docs auto-generated)

`/nodes`, `/nodes/{id}/telemetry`, `/incidents`, `/incidents/{id}/ack`, `/incidents/{id}/dispatch`, `/incidents/{id}/forecast`, `/incidents/{id}/route?from=lat,lon`, `/stations`, `/risk-map` (tiles or GeoJSON from placement), `/subscriptions` (public resident opt-in, rate-limited), `/ws` (live events).

### Done when

`docker compose up` + simulator scenario → an incident is created, the station is notified, escalation works, and the audit log shows every step. Integration tests cover the state machine, watchdog thresholds, HMAC rejection and escalation.

## 9. `web/` — Progressive Web App (P1)

### Stack

React + TypeScript + Vite · `vite-plugin-pwa` (Workbox) · React Leaflet + OpenStreetMap tiles · TanStack Query · Tailwind · i18next with **Arabic (RTL), French, English**.

### Views

1. **Station dashboard** (desktop, big screen)
   - Full-screen map: nodes coloured by state (normal / alert / fire / offline / lost-burned), last contact on hover, battery indicator.
   - Layers toggle: risk map from placement, node detection radii, gateways, access points, villages.
   - Incident panel: timeline from the audit log, **Acknowledge** button, assign crew.
   - Spread overlay with a **time slider** (now → +2 h), probability contours, suggested firebreak (dashed, labelled advisory).
   - Loud audio + flashing banner on new incident (browser autoplay rules: require one click to "arm" the station screen at shift start).
   - Night mode by default after sunset.
2. **Crew mobile** (phone, used in a moving vehicle)
   - One screen per incident: distance, estimated fire zone, access point.
   - Huge **Go** button → opens Google Maps / Waze deep link to the access point (`https://www.google.com/maps/dir/?api=1&destination=LAT,LON&travelmode=driving`), with in-app fallback route drawing.
   - Status buttons: En route · On site · Under control · False alarm. Large touch targets (≥ 56 px), usable with gloves.
   - **Offline first:** app shell cached; map tiles for the crew's zone pre-cached at login; status updates queued with background sync when signal is lost.
3. **Admin**
   - Node registry (install, move, retire), maintenance tickets from `OFFLINE` nodes, packet loss per node, battery trends (the sustainability story).
   - Stations, crews, users.
4. **Public resident page**
   - Opt-in form: phone, zone (pick on map), language, explicit consent text, unsubscribe link. Mobile-first, Arabic default.
   - Public risk map for the community (no node-level live data).

### Notifications

Web Push with VAPID keys (works on Android and on iOS 16.4+ when the app is installed to the home screen). Always duplicate critical alerts through the station siren; never rely on push alone.

### Done when

Lighthouse PWA installable, one Playwright test covers: simulated fire → dashboard alert → acknowledge → crew Go → status updates → incident closed.

## 10. `simulator/` — the demo engine (P1, high value)

Until firmware exists, the simulator **is** the sensing layer. It publishes exactly the §5 contract, signed with node keys.

- Virtual nodes loaded from `placement/` output (`nodes.geojson`) so the demo uses real optimised locations.
- Realistic signals: daily temperature/humidity cycles, sensor noise, slow gas-sensor drift, battery charge/discharge with a solar curve.
- **Closed-loop fire scenarios:** the simulator uses the `spread` engine with hidden "true" parameters to decide when smoke reaches each node, then emits `ALERT` → `FIRE` → silence (`LOST_PROBABLY_BURNED`). The backend's engine must recover the fire without knowing those parameters. This is a strong, honest demo of the prediction engine.
- Scenarios (`simulator/scenarios/*.yaml`):
  - `normal_day` — heartbeats only.
  - `false_alarm_fog` — humidity spike, gas dip, no flame → should stay `ALERT`, never `FIRE`.
  - `melloula_replay` — ignition near a road in the pilot zone, wind from the west, two nodes detect, one burns.
  - `node_failure` — a node goes silent in `NORMAL` → maintenance ticket after 60 min (time-accelerated).
  - `unacknowledged` — nobody acknowledges → escalation after 3 min.
- `--speed 60` time acceleration so a 1-hour scenario fits in 1 minute of demo.

## 11. The 2-minute Phase 2 demo (write `docs/demo-script.md` early)

1. Map of Kroumirie with the risk layer and optimised nodes (placement model).
2. Start `melloula_replay`: a node turns orange, then red; station siren and dashboard alarm.
3. Dispatcher acknowledges; crew phone shows the incident, driver presses **Go**.
4. Spread forecast appears; a second node detects and the forecast sharpens; the first node is marked "lost, probably burned".
5. Suggested firebreak line between the front and the village (advisory).
6. Resident SMS shown in the console provider, in Arabic.
7. One real hardware node (when firmware exists) triggers the same flow from real smoke.

Everything must run offline on one laptop (local tiles cache, mock routing and SMS providers).

## 12. Milestones

| Dates | Milestone |
|---|---|
| now → 8 Oct | `placement/` v1: pipeline, metrics, all report figures |
| 8 → 12 Oct | Buffer for the report; freeze figures |
| 13 → 26 Oct | `contracts/`, backend skeleton, database, MQTT ingest, simulator `normal_day` |
| 27 Oct → 9 Nov | Incident manager, escalation, station dashboard, crew app, routing |
| 10 → 23 Nov | `spread/` engine + particle filter + closed-loop scenarios |
| 24 Nov → 3 Dec | Firmware integration (separate track), PWA offline, i18n, README, CI |
| 4 → 10 Dec | Demo rehearsal, recordings, screenshots, final polish |

## 13. README checklist (5 GitHub points)

- One-paragraph pitch, the problem in two numbers, the architecture diagram (Mermaid).
- `docker compose up` + `make demo` quickstart that works on a fresh machine.
- Screenshots / GIF of the demo flow.
- Results section: placement metrics, classifier metrics (later), spread validation.
- SDGs addressed (13, 15, 11, 8), ethics and data-protection notes.
- CI badge, license (MIT or Apache-2.0), contribution notes.
- No names, no school, no Student Branch.

## 14. How Claude should work in this repo

- Start by reading this file and `contracts/`. If a change affects a contract, update `contracts/` first and note it in an ADR.
- Prefer small, reviewable steps; propose a plan before large refactors.
- Keep it simple: no microservices, no Kubernetes, no extra infrastructure the demo does not need.
- Write tests alongside code; for geospatial code, test on tiny synthetic grids with known answers.
- Never fabricate data, results or citations. Mark every assumed parameter as `# ASSUMPTION:` with a source or a note.
- When producing anything that ends up in the report (figure, metric, table), save it under `docs/figures/` with the shared style and state in the commit message which report section it feeds.
- Surface trade-offs briefly in `docs/adr/`; judges reward visible methodology.
- Ask before adding a dependency that needs an API key or a paid service; always provide a mock or free alternative.
