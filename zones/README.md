# zones/ — population alert zones

Builds the inhabited zones around the Kroumirie forest that a public fire alert would target,
and links each zone to the fire risk next to it and to the cell towers that would carry the
alert by Cell Broadcast ([ADR 0003](../docs/adr/0003-cell-broadcast-alert-zones.md)).

```bash
# from the repo root
python -m zones.pipeline --download     # first run: WorldPop grid + OpenCelliD towers
python -m zones.pipeline                # rebuild from the files already in data/raw/
python -m wamidh_backend.load_zones # copy the result into the database
```

## Steps

1. **Settlements.** OSM building footprints plus the WorldPop 2020 constrained cells with at
   least one person. They are clustered with DBSCAN (`eps_m`, `min_buildings`), then buffered
   and simplified into outlines. OSM alone maps only about 11 % of the residents here, so the
   WorldPop cells are needed to find most villages.
2. **Names.** The nearest OSM place within `radius_m` (Arabic, from the OSM `name` field).
   Otherwise the zone is a douar named after the nearest place ("douar near X").
3. **Population.** The sum of the WorldPop people per pixel inside the outline, rounded to 10.
   It is a model estimate, not a census.
4. **Risk.** The highest susceptibility percentile from the placement model
   (`data/processed/susceptibility_kroumirie.tif`, band 2) within `ring_m` of the zone:
   `high` at 80 or more, `medium` at 60 or more (ASSUMPTION thresholds).
5. **Towers.** OpenCelliD cells for Tunisia (MCC 605) within the area plus `pad_m`. A zone is
   served by every tower whose coverage circle intersects it, with the range clipped to
   300–10,000 m. A zone with no such tower gets the nearest one. OpenCelliD positions and
   ranges are crowdsourced estimates.

Thresholds and paths: `config/kroumirie.yaml`. Every value marked `ASSUMPTION` is a choice to
revisit with the Civil Protection and the operators.

## OpenCelliD key

The tower download needs a free OpenCelliD token. Put it in `.env` at the repo root as
`OPENCELLID_API_KEY=...`, or set the environment variable. The key is never printed or
committed. Without it the pipeline still builds the zones and reports
"towers: not available".

## Outputs (`data/processed/`)

- `zones.geojson`: id (by population, largest first), name, near, population, risk_level,
  risk_percentile, tower_ids, building_count.
- `towers.geojson`: id (`mcc-net-area-cell`), radio, net, range_m, samples.
- `zones_summary.json`: counts and the share of the WorldPop population inside the zones.

Latest run: 143 zones, about 131,110 residents (about 90 % of WorldPop's 144,943 in the
area). Risk: 103 high, 30 medium, 10 low.

Towers: 0. The OpenCelliD export for Tunisia (1,958 cells) has none within 30 km of the pilot
zone; the nearest are 43 km away. Alerts are therefore targeted by the zone outlines, as
operators do in practice (ADR 0003). The tower code stays: it links towers as soon as the
data has some (field logging, operator data).

## Tests

```bash
python -m pytest zones/tests
```

The tests run on small synthetic data with known answers: clusters, names, population, risk,
tower parsing and the zone → tower links.
