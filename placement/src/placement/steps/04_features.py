"""Step 04 — per-cell predictors.

Terrain (SRTM), land cover fractions (WorldCover), summer NDVI (Sentinel-2), climate
normals (ERA5-Land) and human-access distances (OpenStreetMap roads/tracks/paths/places,
WorldCover built-up and cropland edges). Plus fire-history features (placement.history)
for two windows of equal length: training (e.g. 2001-2016) and deployment (e.g. 2010-2025).

Outputs (data/interim/): features.parquet (static predictors), history_train.parquet,
history_deploy.parquet (cell_id + fire-history predictors).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from placement.features import (
    distance_to_lines,
    distance_to_mask,
    distance_to_points,
    fill_nan_nearest,
    sample_raster,
)
from placement.grid import Grid, aggregate_mean
from placement.history import HistoryWindows, history_features, in_window, rank_normalise
from placement.io import Raster, read_raster, step_main

log = logging.getLogger("placement.features")

LANDCOVER_FEATURES = ["lc_tree", "lc_shrub", "lc_grass", "lc_crop", "lc_built"]
CLIMATE_FEATURES = ["tmax_c", "wind_speed_ms", "precip_mm_yr"]


def _osm(path: Any, cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    w, s, e, n = cfg["study_area"]["bbox"]
    pad = 0.05  # degrees; lets edge cells find features just outside the box
    gdf = gpd.read_file(path, bbox=(w - pad, s - pad, e + pad, n + pad), columns=["fclass"])
    return gdf.to_crs(cfg["crs"]["metric"])


def build_history(cfg: dict[str, Any]) -> None:
    interim = cfg["paths"]["interim"]
    hc = cfg["fire_history"]
    w = HistoryWindows.from_years(hc["first_year"], hc["history_end_year"], hc["last_year"])
    cells = pd.read_parquet(interim / "cells.parquet")
    ign = pd.read_parquet(interim / "fires_ignitions.parquet")
    det = pd.read_parquet(interim / "fires_clean.parquet")
    for name, start, end in [
        ("train", w.train_start, w.train_end),
        ("deploy", w.deploy_start, w.deploy_end),
    ]:
        feats = history_features(
            cells, ign[in_window(ign, start, end)], det[in_window(det, start, end)], hc["radii_m"]
        )
        log.info(
            "history_%s (%d-%d): raw mean fire starts within 5 km per cell %.2f",
            name,
            start,
            end,
            feats["hist_ign_5km"].mean(),
        )
        # Ranks within the window: removes the level shift between windows (more VIIRS years).
        feats = rank_normalise(feats, [c for c in feats.columns if c != "cell_id"])
        feats.to_parquet(interim / f"history_{name}.parquet")


def run(cfg: dict[str, Any]) -> None:
    build_static(cfg)
    build_history(cfg)


def build_static(cfg: dict[str, Any]) -> None:
    raw_dir, interim = cfg["paths"]["raw"], cfg["paths"]["interim"]
    fc = cfg["features"]
    cells = pd.read_parquet(interim / "cells.parquet")
    grid = Grid(**json.loads((interim / "grid.json").read_text(encoding="utf-8")))
    r, c = cells.row.to_numpy(), cells.col.to_numpy()
    x, y = cells.x.to_numpy(), cells.y.to_numpy()

    def cell_mean(arr: np.ndarray, src: Raster) -> np.ndarray:
        return aggregate_mean(arr, src.transform, grid)[r, c]

    feats = pd.DataFrame({"cell_id": cells.cell_id})

    terrain = read_raster(raw_dir / "gee" / "study_terrain.tif")
    feats["elevation_m"] = cell_mean(terrain.bands["elevation"], terrain)
    feats["slope_deg"] = cell_mean(terrain.bands["slope"], terrain)
    aspect = np.deg2rad(terrain.bands["aspect"])
    feats["aspect_sin"] = cell_mean(np.sin(aspect), terrain)  # east-facing > 0
    feats["aspect_cos"] = cell_mean(np.cos(aspect), terrain)  # north-facing > 0

    lc = read_raster(raw_dir / "gee" / "study_landcover.tif")
    for name in LANDCOVER_FEATURES:
        feats[name] = cell_mean(lc.bands[name], lc)

    ndvi = read_raster(raw_dir / "gee" / "study_ndvi.tif")
    feats["ndvi_summer"] = cell_mean(ndvi.bands["ndvi"], ndvi)

    climate = read_raster(raw_dir / "gee" / "study_climate.tif")
    for name in CLIMATE_FEATURES:
        # ERA5-Land has no data over the sea; coastal cells take the nearest land value.
        feats[name] = sample_raster(fill_nan_nearest(climate.bands[name]), climate.transform, x, y)

    roads = _osm(raw_dir / "osm" / "gis_osm_roads_free_1.shp", cfg)
    for feature, classes in [
        ("dist_road_m", fc["road_classes"]),
        ("dist_track_m", fc["track_classes"]),
        ("dist_path_m", fc["path_classes"]),
    ]:
        lines = roads[roads.fclass.isin(classes)].geometry.to_numpy()
        feats[feature] = distance_to_lines(x, y, lines)
        log.info("%s from %d OSM segments", feature, len(lines))

    places = _osm(raw_dir / "osm" / "gis_osm_places_free_1.shp", cfg)
    places = places[places.fclass.isin(fc["place_classes"])]
    feats["dist_place_m"] = distance_to_points(x, y, places.geometry.centroid.to_numpy())

    for feature, band, threshold in [
        ("dist_builtup_m", "lc_built", fc["builtup_min_fraction"]),
        ("dist_cropland_m", "lc_crop", fc["cropland_min_fraction"]),
    ]:
        mask = np.nan_to_num(lc.bands[band], nan=0.0) >= threshold
        feats[feature] = sample_raster(distance_to_mask(mask, lc.pixel_m), lc.transform, x, y)

    feats.to_parquet(interim / "features.parquet")
    log.info("features for %d cells:\n%s", len(feats), feats.describe().T.round(2).to_string())
    n_nan = feats.isna().sum()
    if n_nan.any():
        log.warning("missing values per feature:\n%s", n_nan[n_nan > 0].to_string())


if __name__ == "__main__":
    step_main(run, "Step 04 - per-cell features")
