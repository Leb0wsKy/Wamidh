# Alert zones and Cell Broadcast: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** population alert zones linked to fire risk and cell towers, a public Residents map, and
Arabic CAP alerts broadcast (simulated) after the dispatcher confirms.

**Architecture:**
- **Offline:** a `zones/` package computes the zones and tower links into GeoJSON.
- **Backend:** loads them into PostGIS, finds the zones concerned by a fire, builds the CAP
  message and sends it through a provider interface (simulated).
- **Web:** shows them on the Residents tab and in the incident view.

**Tech stack:** geopandas, scikit-learn (DBSCAN), rasterio, shapely; FastAPI, SQLAlchemy, PostGIS,
Alembic; React, react-leaflet, vitest.

**Spec:** `docs/superpowers/specs/2026-10-05-alert-zones-cell-broadcast-design.md`. **ADR:** `docs/adr/0003-cell-broadcast-alert-zones.md`.

## Global constraints

- **Assumptions:** every threshold lives in YAML and is marked `ASSUMPTION`. No invented data:
  population is labelled "estimate", towers "approximate".
- **Secrets:** the OpenCelliD key comes from the environment or `.env` and is never printed in
  full or committed.
- **No automatic broadcast:** only `POST /incidents/{id}/alert` sends, and only after
  acknowledgement.
- **Alert language:** Arabic (`ar-TN`). CAP 1.2 namespace `urn:oasis:names:tc:emergency:cap:1.2`.
- **Coordinates:** WGS84 stored; distances on geography or EPSG:32632.

## Review focus

1. **No OpenCelliD key yet:** the pipeline must still produce zones, with "towers: not available"; the Residents map must still work. Test: `test_pipeline_without_towers`.
2. **A fire far from every zone:** the proposal is empty and the broadcast is refused with a clear 409, not a 500. Test: `test_alert_refused_without_zones`.
3. **Broadcast before acknowledgement:** refused with 409. Test: `test_alert_refused_before_ack`.
4. **CAP polygons** in "lat,lon" order and closed: operators reject anything else. Test: `test_cap_polygons_lat_lon_closed`.
5. **A multi-part zone** (a MultiPolygon after buffering): every part goes into the CAP and onto the map. Test: `test_multipart_zone_in_cap`.

---

### Task 1: `zones/` package (clusters, names, population, risk, towers, pipeline)

- **Tests (synthetic):**
  - `test_clusters_two_groups_drop_isolated`;
  - `test_name_nearest_place_and_douar_fallback`;
  - `test_population_sum_inside_outline`;
  - `test_risk_level_from_toy_raster`;
  - `test_parse_towers_with_and_without_header`;
  - `test_parse_towers_bad_format_fails_clearly`;
  - `test_zone_towers_intersection_then_nearest`;
  - `test_pipeline_without_towers`.
- **Implementation:**
  - `zones/pyproject.toml`, `zones/config/kroumirie.yaml`;
  - modules `config.py`, `download.py`, `clusters.py`, `population.py`, `risk.py`, `towers.py`, `pipeline.py`.
- **Run:** `cd zones && ../.venv/Scripts/python -m pytest -q`, plus ruff.

### Task 2: backend migration 0002, loader, `zones_near`, public alert storage

- **Tests:**
  - integration `test_load_zones_and_towers`;
  - `test_zones_near_order_and_radius`;
  - `test_public_alert_round_trip`;
  - unit (SQLite) `test_zones_near_needs_postgresql`.
- **Implementation:**
  - migration `0002_alert_zones.py`;
  - models `AlertZoneRow`, `CellTowerRow`, `ZoneTowerRow`, `PublicAlertRow`;
  - `load_zones.py`;
  - `Store.zones_near`, `save_public_alert`, `list_public_alerts`.

### Task 3: alert service, CAP, provider, API

- **Tests:**
  - `test_proposal_people_towers_and_arabic_text`;
  - `test_cap_is_valid_cap_1_2_in_arabic`;
  - `test_cap_polygons_lat_lon_closed`;
  - `test_multipart_zone_in_cap`;
  - API: `test_alert_refused_before_ack`, `test_alert_refused_without_zones`, `test_alert_sent_logged_and_public`.
- **Implementation:**
  - `alerts.py`, `broadcast.py`;
  - `backend/config/alerts.yaml`;
  - the `create_app` parameters `zones_store`, `broadcast`, `alerts_cfg`;
  - the endpoints, and `contracts/api.md`.

### Task 4: web (Residents tab, incident "Population" section)

- **Tests:**
  - `ZonePanel` contents;
  - `AlertCard` Arabic text and "simulation" label;
  - `IncidentPopulation`: button disabled before acknowledgement, confirm step, sent state.
- **Implementation:**
  - types and queries (`useZones`, `useTowers`, `useActiveAlerts`, `useAlertProposal`, `useSendAlert`);
  - `ResidentsPage`, `ZonesMap`, `ZonePanel`, `AlertCard`, `IncidentPopulation`;
  - i18n in fr, ar and en.

### Task 5: run on real data, live check, docs

- Run the zones pipeline (towers when the key is present), then `load_zones`, then restart the
  backend.
- Live check in Edge: the Residents map; a test fire near a village; the proposal; the confirmed
  broadcast appears on Residents.
- Docs: `zones/README.md`, `backend/README.md`, `data/README.md` (sources and licences), and
  CLAUDE.md (pointer to ADR 0003).
