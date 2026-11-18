"""Step 07 — ignition-susceptibility map for every wildland cell.

Uses the final model from step 06 with static features + fire history from the
*deployment* window (the latest years, same length as the training window).

Values:
  susceptibility  calibrated score in [0, 1]. Calibrated on a 1:1 fire/no-fire sample, so it
                  is a *relative* susceptibility, not an absolute annual probability.
  percentile      rank of the cell among all wildland cells of northern Tunisia (0-100),
                  from the uncalibrated score (isotonic calibration creates ties).

Outputs (data/processed/): susceptibility.parquet, susceptibility_north.tif,
susceptibility_<pilot>.tif (bands: susceptibility, percentile).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import joblib
import pandas as pd
from pyproj import Transformer
from scipy.stats import rankdata

from placement.grid import Grid
from placement.history import HistoryWindows
from placement.io import step_main, write_geotiff, write_json

log = logging.getLogger("placement.predict")


def run(cfg: dict[str, Any]) -> None:
    interim, processed = cfg["paths"]["interim"], cfg["paths"]["processed"]
    hc = cfg["fire_history"]
    w = HistoryWindows.from_years(hc["first_year"], hc["history_end_year"], hc["last_year"])
    bundle = joblib.load(processed / "model.joblib")
    grid = Grid(**json.loads((interim / "grid.json").read_text(encoding="utf-8")))

    cells = pd.read_parquet(interim / "cells.parquet")
    data = cells.merge(pd.read_parquet(interim / "features.parquet"), on="cell_id").merge(
        pd.read_parquet(interim / "history_deploy.parquet"), on="cell_id"
    )
    raw = bundle["model"].predict_proba(data[bundle["features"]])[:, 1]
    data["score_raw"] = raw
    data["susceptibility"] = bundle["calibrator"].predict(raw)
    data["percentile"] = 100.0 * (rankdata(raw) - 1) / (len(raw) - 1)

    out = data[
        [
            "cell_id",
            "row",
            "col",
            "x",
            "y",
            "lon",
            "lat",
            "governorate",
            "score_raw",
            "susceptibility",
            "percentile",
        ]
    ]
    out.to_parquet(processed / "susceptibility.parquet")

    tags = {
        "model": bundle["name"],
        "history_window": f"{w.deploy_start}-{w.deploy_end}",
        "susceptibility": "calibrated on a 1:1 sample; relative, not an absolute probability",
        "percentile": "rank among wildland cells of northern Tunisia, 0-100",
    }
    rows, cols = out.row.to_numpy(), out.col.to_numpy()
    bands = {
        "susceptibility": grid.to_raster(rows, cols, out.susceptibility.to_numpy()),
        "percentile": grid.to_raster(rows, cols, out.percentile.to_numpy()),
    }
    crs = cfg["crs"]["metric"]
    write_geotiff(processed / "susceptibility_north.tif", bands, grid.transform, crs, tags)

    # Pilot zone cut-out.
    pz = cfg["pilot_zone"]
    to_utm = Transformer.from_crs(cfg["crs"]["storage"], crs, always_xy=True)
    w_, s, e, n = pz["bbox"]
    px, py = to_utm.transform([w_, e, e, w_], [s, s, n, n])
    (r0, r1, c0, c1), sub = grid.window(min(px), min(py), max(px), max(py))
    pilot_bands = {k: v[r0:r1, c0:c1] for k, v in bands.items()}
    write_geotiff(
        processed / f"susceptibility_{pz['name']}.tif", pilot_bands, sub.transform, crs, tags
    )

    in_pilot = (rows >= r0) & (rows < r1) & (cols >= c0) & (cols < c1)
    pilot = out[in_pilot]
    summary = {
        "cells": len(out),
        "pilot_cells": int(in_pilot.sum()),
        "pilot_share_in_national_top20pct": float((pilot.percentile >= 80).mean()),
        "pilot_median_percentile": float(pilot.percentile.median()),
        "by_governorate_median_percentile": out.groupby("governorate")
        .percentile.median()
        .round(1)
        .to_dict(),
    }
    write_json(processed / "susceptibility_summary.json", summary)
    log.info("susceptibility map: %s", json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    step_main(run, "Step 07 - susceptibility map")
