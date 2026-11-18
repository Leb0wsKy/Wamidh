# Alert zones, cell towers and Cell Broadcast alerts (Residents tab)

- **Date:** 2026-10-05
- **Decision record:** [ADR 0003](../../adr/0003-cell-broadcast-alert-zones.md)
- **Scope:** a new offline pipeline `zones/`, the backend (migration, loader, API, alert service),
  the web app (Residents tab, alert in the incident view) and docs.

## 1. Zones pipeline (`zones/`, offline, like `placement/`)

`python -m zones.pipeline --config zones/config/kroumirie.yaml`. All thresholds live in that YAML
and are marked `ASSUMPTION`.

1. **Download (once).**
   - WorldPop 2020 constrained population for Tunisia (`tun_ppp_2020_constrained.tif`,
     about 5.8 MB) into `data/raw/worldpop/`.
   - OpenCelliD towers of Tunisia (MCC 605) with the key from `OPENCELLID_API_KEY`
     (environment or `.env`) into `data/raw/opencellid/605.csv.gz`. If the key is missing, the
     step stops with a clear message; the other steps still run, and the outputs say "towers:
     not available".
2. **Clusters.**
   - **Input:** OSM building footprints in the pilot bounding box. Their centroids are projected
     to EPSG:32632.
   - **Clustering:** DBSCAN with `eps_m` = 150 and `min_buildings` = 5.
   - **Outline:** the union of 60 m buffers around the cluster's buildings (`buffer_m`),
     simplified to 10 m and returned to WGS84.
3. **Names.** The nearest OSM place (town, village, hamlet, suburb) within `name_radius_m`
   (2,000 m) gives the name, in Arabic and Latin when OSM has both. Otherwise "douar near X"
   with the nearest place.
4. **Population.** The sum of WorldPop pixels whose centre falls inside the outline, rounded to
   the nearest 10, and labelled "estimate".
5. **Risk.** The maximum `percentile` (band 2 of `susceptibility_<pilot>.tif`) over wildland
   cells within `risk_ring_m` (1,000 m) of the outline:
   - **high** at 80 or above;
   - **medium** at 60 or above;
   - **low** otherwise;
   - **none** if no forest lies within the ring.
6. **Towers.**
   - **Parsing:** the CSV is parsed, keeping towers inside the bounding box plus 5 km.
   - **Columns:** radio, mcc, net, area, cell, unit, lon, lat, range, samples, changeable,
     created, updated, averageSignal. A header row is accepted, and a different format stops
     the step with a clear message.
   - **Coverage:** a circle of `range` metres, clipped between 300 and 10,000 m.
   - **Links:** a zone is served by the towers whose circle intersects its outline; if none do,
     by the nearest tower.
7. **Outputs:**
   - `data/processed/zones.geojson`: id, name, name_ar, population, risk_level,
     risk_percentile, tower_ids, building_count.
   - `data/processed/towers.geojson`: id = "mcc-net-area-cell", radio, net, range_m, samples.
   - `zones_summary.json`: counts, people covered, and zones without a tower.

## 2. Backend

- **Migration 0002:**
  - `alert_zone(id, name, name_ar, population, risk_level, risk_percentile, building_count,
    outline geography(MultiPolygon,4326))`, with a GiST index;
  - `cell_tower(id text, radio, net, range_m, samples, location geography(Point,4326))`;
  - `zone_tower(zone_id, tower_id)`;
  - `public_alert(id, incident_id, created_at, confirmed_by, zone_ids json, tower_ids json,
    people int, message_ar text, cap_xml text, delivery text, status text)`.
- **Loader:** `python -m wamidh_backend.load_zones` replaces zones and towers from the two
  GeoJSON files, in one transaction.
- **Store:**
  - `zones_near(lon, lat, radius_km)` returns each zone with its distance and towers, nearest
    first, using `ST_DWithin` on geography;
  - plus save, list and load for public alerts.
- **Alert service** (`alerts.py`, pure, tested):
  - `propose(incident, zones) -> Proposal`: the zones, people, towers and Arabic text;
  - `cap_xml(proposal, now, exercise) -> str`.
- **Arabic templates** in `backend/config/alerts.yaml`:
  - `headline`, `description` and `instruction` with `{zones}` and `{km}`;
  - the radius `concern_radius_km` = 3 (`ASSUMPTION`).
- **Delivery:** the protocol `BroadcastProvider.send(cap_xml, tower_ids) -> str`.
  `SimulatedBroadcast` logs the message and returns "simulated".
- **API:**
  - `GET /zones`: a FeatureCollection, public.
  - `GET /towers`: a FeatureCollection, public.
  - `GET /incidents/{id}/alert-proposal`: the zones, people, towers and Arabic text. Returns
    404 if the incident doesn't exist; an empty list if no zone is concerned.
  - `POST /incidents/{id}/alert {confirmed_by}`:
    - **Precondition:** the incident must be acknowledged (409 otherwise); a zone list must
      exist (409 if empty).
    - **Effect:** it builds the CAP, sends it through the provider, stores a `public_alert`,
      and appends an audit event `public_alert` (zones, people, confirmed_by).
    - **Repeats:** a second alert for the same incident is allowed, as an update.
  - `GET /alerts?active=true`: public alerts of incidents not yet closed, newest first, in
    Arabic text with zone names. No sensor or personal data.
  - **No automatic broadcast** anywhere: the core never calls the provider.

## 3. Web

- **Residents tab** (`/residents`, public, Arabic by default for a first-time visitor):
  - **A dedicated map:**
    - zones as polygons coloured by risk level;
    - towers as small antenna markers;
    - each tower's coverage as a light circle;
    - zone → tower links on hover or click.
  - **Side panel:** the selected zone's name (Arabic and Latin), estimated population, risk
    level, serving towers, and its active alert.
  - **"Alertes en cours":** each alert's text as received, on a simulated phone card labelled
    "simulation".
  - **Legend:** risk levels and data sources (OSM, WorldPop, OpenCelliD, placement model).
- **Incident detail (Incidents tab):** a "Population" section.
  - **Contents:** the concerned zones (distance, people, towers) and the Arabic preview.
  - **Button:** "Diffuser l'alerte", enabled only once the incident is acknowledged, with a
    confirm step.
  - **After sending:** "Alerte diffusée à HH:MM (simulation)".
- **Languages:** text in fr, ar and en; the alert text itself is always Arabic.

## 4. Tests

- **`zones`** (synthetic data, small and known):
  - two groups of buildings make two clusters and isolated houses are dropped;
  - naming from the nearest place, and the "douar near" fallback;
  - population sum inside the outline;
  - risk level from a toy raster;
  - tower parsing (with and without header; a bad format fails clearly);
  - zone → towers (intersection, then nearest).
- **Backend:**
  - the loader;
  - `zones_near` order and radius (PostgreSQL integration);
  - the proposal text and people;
  - CAP: valid XML, the CAP 1.2 namespace, the required elements, Arabic `ar-TN` info,
    polygons in "lat,lon" order and closed;
  - broadcast refused before acknowledgement and with no zones;
  - the audit event written;
  - `/alerts` public content.
- **Web:** zone panel contents, the alert card, the broadcast button disabled until
  acknowledged, and the confirm flow.
- **Live:** the pipeline runs on real data (towers once the key is present); a test fire near a
  village shows the proposal; the broadcast appears on the Residents tab.

## 5. Out of scope

- A real operator Cell Broadcast Centre.
- Wind- and terrain-aware concerned zones (comes with the spread engine).
- Translating the alert into French: Arabic is the decision; French can be added to the CAP as a
  second `info` block later.
