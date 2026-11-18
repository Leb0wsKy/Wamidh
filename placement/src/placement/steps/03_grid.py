"""Step 03 — 375 m analysis grid over the wildland of northern Tunisia.

A cell is kept if it lies in one of the configured governorates and at least
`min_wildland_fraction` of it is tree cover, shrubland or grassland (WorldCover).

Outputs (data/interim/): grid.json (grid geometry), cells.parquet (one row per kept cell).
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from placement.grid import Grid, aggregate_mean
from placement.io import WORLDCOVER_CLASSES, normalise_name, read_raster, step_main, write_json

log = logging.getLogger("placement.grid")


def run(cfg: dict[str, Any]) -> None:
    raw_dir, out_dir = cfg["paths"]["raw"], cfg["paths"]["interim"]
    gc = cfg["grid"]
    lc = read_raster(raw_dir / "gee" / "study_landcover.tif")

    any_band = next(iter(lc.bands.values()))
    h, w = any_band.shape
    t = lc.transform
    grid = Grid.covering(t.c, t.f + h * t.e, t.c + w * t.a, t.f, gc["cell_size_m"])

    wild_px = sum(lc.bands[f"lc_{WORLDCOVER_CLASSES[c]}"] for c in gc["wildland_classes"])
    wild = aggregate_mean(np.asarray(wild_px), t, grid)
    rows, cols = np.nonzero(wild >= gc["min_wildland_fraction"])
    x, y = grid.centres(rows, cols)
    to_ll = Transformer.from_crs(cfg["crs"]["metric"], cfg["crs"]["storage"], always_xy=True)
    lon, lat = to_ll.transform(x, y)

    cells = gpd.GeoDataFrame(
        {
            "cell_id": rows * grid.ncols + cols,
            "row": rows,
            "col": cols,
            "x": x,
            "y": y,
            "lon": lon,
            "lat": lat,
            "wildland_frac": wild[rows, cols],
        },
        geometry=gpd.points_from_xy(x, y),
        crs=cfg["crs"]["metric"],
    )
    govs = gpd.read_file(raw_dir / "boundaries" / "tun_adm1.geojson").to_crs(cfg["crs"]["metric"])
    wanted = {normalise_name(g) for g in cfg["study_area"]["governorates"]}
    govs = govs[govs.shapeName.map(normalise_name).isin(wanted)]
    missing = wanted - set(govs.shapeName.map(normalise_name))
    if missing:
        raise SystemExit(f"Governorates not found in boundaries: {sorted(missing)}")

    joined = gpd.sjoin(cells, govs[["shapeName", "geometry"]], predicate="within", how="inner")
    out = pd.DataFrame(joined.drop(columns=["geometry", "index_right"]))
    out = out.rename(columns={"shapeName": "governorate"}).sort_values("cell_id")
    out = out.reset_index(drop=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_dir / "cells.parquet")
    write_json(out_dir / "grid.json", asdict(grid))
    by_gov = out.governorate.value_counts().to_dict()
    log.info("grid %dx%d, %d wildland cells kept: %s", grid.nrows, grid.ncols, len(out), by_gov)


if __name__ == "__main__":
    step_main(run, "Step 03 - analysis grid")
