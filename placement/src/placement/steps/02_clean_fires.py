"""Step 02 — clean FIRMS detections and group them into fire events.

Outputs (data/interim/):
  fires_all.parquet        every detection in the study box, normalised (used to keep burned
                           cells out of the negative sample)
  fires_clean.parquet      detections kept after all filters, with event_id
  fires_ignitions.parquet  one row per event: earliest detection = ignition proxy
  fires_cleaning.json      row counts after each filter (reported in the methodology)

fires_all.parquet keeps detections just across the Algerian border too, so border cells that
burned are still kept out of the negative sample.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

from placement.features import window_mean
from placement.fires import cluster_events, filter_detections, ignitions, normalise
from placement.io import read_raster, step_main, write_json

log = logging.getLogger("placement.clean_fires")


def _source_of(path: Path, df: pd.DataFrame) -> str:
    if path.name.upper().startswith("VIIRS") or "bright_ti4" in df.columns:
        return "VIIRS"
    return "MODIS"


def load_detections(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted((raw_dir / "firms").glob("*/*.csv")):
        try:
            raw = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            continue
        if raw.empty:
            continue
        frames.append(normalise(raw, _source_of(path, raw)))
    if not frames:
        raise SystemExit(f"No FIRMS CSVs under {raw_dir / 'firms'}; run step 01 first.")
    df = pd.concat(frames, ignore_index=True)
    # API and manual archive downloads can overlap.
    return df.drop_duplicates(["source", "lat", "lon", "time"]).reset_index(drop=True)


def run(cfg: dict[str, Any]) -> None:
    raw_dir, out_dir = cfg["paths"]["raw"], cfg["paths"]["interim"]
    out_dir.mkdir(parents=True, exist_ok=True)
    fc = cfg["fires"]
    counts: dict[str, Any] = {}

    df = load_detections(raw_dir)
    w, s, e, n = cfg["study_area"]["bbox"]
    df = df[df.lon.between(w, e) & df.lat.between(s, n)].reset_index(drop=True)
    to_utm = Transformer.from_crs(cfg["crs"]["storage"], cfg["crs"]["metric"], always_xy=True)
    df["x"], df["y"] = to_utm.transform(df.lon.to_numpy(), df.lat.to_numpy())
    df.to_parquet(out_dir / "fires_all.parquet")
    counts["1_all_in_study_box"] = df.groupby("source").size().to_dict()

    # The study box also covers a strip of north-east Algeria; keep Tunisian detections only.
    tunisia = gpd.read_file(raw_dir / "boundaries" / "tun_adm1.geojson").union_all()
    df = df[shapely.contains_xy(tunisia, df.lon.to_numpy(), df.lat.to_numpy())]
    df = df.reset_index(drop=True)
    counts["2_inside_tunisia"] = df.groupby("source").size().to_dict()

    df = filter_detections(df, fc)
    counts["3_season_confidence_frp_vegetation"] = df.groupby("source").size().to_dict()

    # Agricultural burning: drop detections whose footprint is mostly cropland.
    lc = read_raster(raw_dir / "gee" / "study_landcover.tif")
    crop = np.full(len(df), np.nan)
    for source, half_m in fc["footprint_half_m"].items():
        sel = (df.source == source).to_numpy()
        crop[sel] = window_mean(
            lc.bands["lc_crop"], lc.transform, df.x[sel].to_numpy(), df.y[sel].to_numpy(), half_m
        )
    df["crop_frac"] = crop
    df = df[df.crop_frac <= fc["cropland_max_fraction"]].reset_index(drop=True)
    counts["4_not_cropland"] = df.groupby("source").size().to_dict()

    t_days = (df.time - df.time.min()).dt.total_seconds().to_numpy() / 86400.0
    db = fc["dbscan"]
    df["event_id"] = cluster_events(
        df.x.to_numpy(), df.y.to_numpy(), t_days, db["eps_m"], db["eps_days"]
    )
    df.to_parquet(out_dir / "fires_clean.parquet")

    ign = ignitions(df)
    ign.to_parquet(out_dir / "fires_ignitions.parquet")
    counts["5_events"] = int(len(ign))
    counts["events_by_first_source"] = ign.groupby("source").size().to_dict()
    counts["events_by_year"] = ign.time.dt.year.value_counts().sort_index().to_dict()
    counts["detections_per_event"] = {
        "median": float(ign.n_detections.median()),
        "max": int(ign.n_detections.max()),
    }
    write_json(out_dir / "fires_cleaning.json", counts)
    log.info("cleaning counts: %s", counts)


if __name__ == "__main__":
    step_main(run, "Step 02 - clean FIRMS detections")
