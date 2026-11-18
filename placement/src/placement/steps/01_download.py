"""Step 01 — download raw inputs into data/raw/.

    python -m placement.steps.01_download --config config/pilot_kroumirie.yaml [--only osm ...]

Targets:
  firms       NASA FIRMS standard-processing archive (VIIRS S-NPP 375 m, MODIS 1 km) via the
              area API. Needs a free MAP_KEY in the FIRMS_MAP_KEY environment variable
              (https://firms.modaps.eosdis.nasa.gov/api/map_key/). Alternative: request the
              archive by e-mail from the FIRMS download page and unzip the CSVs into
              data/raw/firms/manual/ — step 02 reads both.
  osm         Geofabrik Tunisia shapefile extract (roads, places, land use).
  boundaries  geoBoundaries ADM1 (governorates).
  gee         Starts Earth Engine export tasks to Google Drive (SRTM, WorldCover, Sentinel-2
              NDVI, ERA5-Land). Needs `earthengine authenticate` once and a Cloud project id
              in EE_PROJECT. When the tasks finish, copy the GeoTIFFs into data/raw/gee/.
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from placement.config import load_config
from placement.firms import fetch_with_backoff, request_windows

log = logging.getLogger("placement.download")
TARGETS = ("firms", "osm", "boundaries", "gee")


def _get(url: str, **kwargs: Any) -> requests.Response:
    resp = requests.get(url, timeout=120, **kwargs)
    resp.raise_for_status()
    return resp


def _firms_get(url: str) -> tuple[int, str]:
    resp = requests.get(url, timeout=120)
    return resp.status_code, resp.text


def _quota_wait(seconds: float) -> None:
    log.info("FIRMS transaction quota reached; waiting %.0f s before retrying", seconds)
    time.sleep(seconds)


def download_firms(cfg: dict[str, Any], out_dir: Path) -> None:
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise SystemExit(
            "FIRMS_MAP_KEY is not set. Get a free key at "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/ or use the manual archive "
            "(see module docstring)."
        )
    fc = cfg["download"]["firms"]
    bbox = ",".join(str(v) for v in cfg["study_area"]["bbox"])
    months = cfg["fires"]["season_months"]
    out_dir.mkdir(parents=True, exist_ok=True)

    for source, years in fc["sources"].items():
        for year in range(years["start_year"], years["end_year"] + 1):
            target = out_dir / f"{source}_{year}.csv"
            if target.exists():
                log.info("skip %s (exists)", target.name)
                continue
            frames = []
            for start, n_days in request_windows(year, year, months, fc["day_range"]):
                url = f"{fc['api_base']}/{key}/{source}/{bbox}/{n_days}/{start.isoformat()}"
                text = fetch_with_backoff(
                    url, _firms_get, sleep=_quota_wait, wait_s=fc["quota_wait_s"]
                )
                df = pd.read_csv(io.StringIO(text))
                if not df.empty:
                    frames.append(df)
                time.sleep(fc["pause_s"])
            year_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
            year_df.to_csv(target, index=False)
            log.info("%s %d: %d detections", source, year, len(year_df))


def download_osm(cfg: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    marker = out_dir / "gis_osm_roads_free_1.shp"
    if marker.exists():
        log.info("skip OSM (exists)")
        return
    url = cfg["download"]["osm"]["url"]
    log.info("downloading %s", url)
    with requests.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        buf = io.BytesIO()
        for chunk in resp.iter_content(chunk_size=1 << 20):
            buf.write(chunk)
    with zipfile.ZipFile(buf) as zf:
        zf.extractall(out_dir)
    log.info("OSM extract unpacked to %s", out_dir)


def download_boundaries(cfg: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "tun_adm1.geojson"
    if target.exists():
        log.info("skip boundaries (exists)")
        return
    meta = _get(cfg["download"]["boundaries"]["api"]).json()
    target.write_bytes(_get(meta["gjDownloadURL"]).content)
    log.info("boundaries: %s (license: %s)", target.name, meta.get("boundaryLicense"))


def start_gee_exports(cfg: dict[str, Any]) -> None:
    from placement import gee_export

    project = os.environ.get("EE_PROJECT")
    if not project:
        raise SystemExit(
            "EE_PROJECT is not set (Google Cloud project registered for Earth Engine)."
        )
    for task_name in gee_export.start_exports(cfg, project):
        log.info("started Earth Engine task: %s", task_name)
    log.info("Track progress at https://code.earthengine.google.com/tasks")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", required=True)
    parser.add_argument("--only", nargs="+", choices=TARGETS, default=list(TARGETS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    raw: Path = cfg["paths"]["raw"]
    if "firms" in args.only:
        download_firms(cfg, raw / "firms" / "api")
    if "osm" in args.only:
        download_osm(cfg, raw / "osm")
    if "boundaries" in args.only:
        download_boundaries(cfg, raw / "boundaries")
    if "gee" in args.only:
        start_gee_exports(cfg)


if __name__ == "__main__":
    main()
