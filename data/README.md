# data/

Raw and derived data are **not committed** (this folder is git-ignored except this file).
Everything here can be re-created with the scripts below, run from `placement/`.

## One-time setup

| What | Why | How |
|---|---|---|
| FIRMS MAP_KEY (free) | fire detections via the FIRMS API | Request at <https://firms.modaps.eosdis.nasa.gov/api/map_key/> |
| Earth Engine access (free for non-commercial use) | SRTM, WorldCover, Sentinel-2, ERA5-Land exports | `earthengine authenticate`, then register a Google Cloud project for Earth Engine |

Set the keys as environment variables (never commit them):

```powershell
# PowerShell (note: `set X=...` does NOT work here)
$env:FIRMS_MAP_KEY = "<key>"
$env:EE_PROJECT = "<project-id>"
```

```bash
# bash / Git Bash
export FIRMS_MAP_KEY=<key>
export EE_PROJECT=<project-id>
```

No FIRMS key? Request the archive by e-mail from <https://firms.modaps.eosdis.nasa.gov/download/>
(country: Tunisia; sources: VIIRS S-NPP 375 m 2012–2025 and MODIS C6.1 2001–2025, CSV) and unzip
the CSVs into `data/raw/firms/manual/`.

## Fetch

```bash
cd placement
python -m placement.steps.01_download --config config/pilot_kroumirie.yaml               # everything
python -m placement.steps.01_download --config config/pilot_kroumirie.yaml --only osm boundaries
```

The `gee` target only **starts** Earth Engine export tasks. When they finish (Earth Engine Tasks
tab), download the GeoTIFFs from the `wamidh_gee` Google Drive folder into `data/raw/gee/`.

## Layout

```
data/
├── raw/
│   ├── firms/api/          VIIRS_SNPP_SP_<year>.csv, MODIS_SP_<year>.csv (fire season only)
│   ├── firms/manual/       optional archive CSVs from the FIRMS download page
│   ├── osm/                Geofabrik Tunisia shapefiles (gis_osm_roads_free_1.shp, ...)
│   ├── boundaries/         tun_adm1.geojson (geoBoundaries gbOpen ADM1)
│   ├── gee/                study_{terrain,landcover,ndvi,climate}*.tif, kroumirie_*.tif
│   ├── worldpop/           tun_ppp_2020_constrained.tif (python -m zones.pipeline --download)
│   └── opencellid/         605.csv.gz (same command; needs OPENCELLID_API_KEY)
├── interim/                outputs of steps 02–05
└── processed/              model, susceptibility GeoTIFF, nodes.geojson, gateways.geojson,
                            zones.geojson, towers.geojson, zones_summary.json (zones/)
```

## Sources and licences

| Layer | Source | Licence |
|---|---|---|
| Active fires | NASA FIRMS (VIIRS S-NPP 375 m SP, MODIS C6.1 SP) | NASA open data; cite FIRMS |
| Elevation | SRTM GL1 v003 (`USGS/SRTMGL1_003`) | Public domain |
| Land cover | ESA WorldCover 2021 v200 (`ESA/WorldCover/v200`) | CC BY 4.0 |
| NDVI | Sentinel-2 L2A (`COPERNICUS/S2_SR_HARMONIZED`) | Copernicus open licence |
| Climate | ERA5-Land daily aggregates (`ECMWF/ERA5_LAND/DAILY_AGGR`) | Copernicus licence |
| Roads, places, land use | OpenStreetMap via Geofabrik | ODbL 1.0 |
| Governorates | geoBoundaries gbOpen TUN ADM1 | ODbL 1.0 |
| Population | WorldPop 2020 constrained, 100 m (`tun_ppp_2020_constrained.tif`) | CC BY 4.0 |
| Cell towers | OpenCelliD bulk export, MCC 605 (needs a free token in `.env`) | CC BY-SA 4.0 |

## `dev/wamidh.db` (legacy)

The SQLite file the backend used until 2026-10-05. Its contents were copied into PostgreSQL
(`python -m wamidh_backend.migrate_sqlite`, ADR 0002); the file is kept unchanged as a
backup and is no longer written to.
