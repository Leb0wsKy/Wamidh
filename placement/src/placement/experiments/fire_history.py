"""Fire history features + temporal validation + repeat-fire weighting.

    python -m placement.experiments.fire_history --config config/pilot_kroumirie.yaml

Features come from fires up to `history_end_year`; labels are fire starts after it, so the
model always predicts the future from the past. Cells that burned only in the history period
may be negatives (otherwise the history features would separate the classes by construction).

Variants, all scored on the same labels and the same leave-one-governorate-out folds:
  A  current features                     unweighted
  B  + fire history features              unweighted
  C  + fire history features              positives weighted by 2017+ event count (capped)

Output: data/processed/fire_history.json
"""

from __future__ import annotations

import argparse
import importlib
import json
from typing import Any

import numpy as np
import pandas as pd
import shapely

from placement.config import load_config
from placement.features import count_within, distance_to_points
from placement.grid import Grid
from placement.io import write_json
from placement.labels import balanced_count_weights, events_per_cell, sample_negatives
from placement.model import capture_rate, cross_validate, make_model

AREA_SHARES = [0.1, 0.2, 0.3]


def history_features(
    cells: pd.DataFrame, hist_ign: pd.DataFrame, hist_det: pd.DataFrame, radii: list[int]
) -> pd.DataFrame:
    """Per-cell fire history from the history period only."""
    x, y = cells.x.to_numpy(), cells.y.to_numpy()
    ix, iy = hist_ign.x.to_numpy(), hist_ign.y.to_numpy()
    out = pd.DataFrame({"cell_id": cells.cell_id})
    for r in radii:
        out[f"hist_ign_{r // 1000}km"] = count_within(x, y, ix, iy, r)
    out["hist_det_1km"] = count_within(x, y, hist_det.x.to_numpy(), hist_det.y.to_numpy(), 1000)
    out["dist_hist_ign_m"] = distance_to_points(x, y, list(shapely.points(ix, iy)))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Fire history + temporal validation")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)
    mc, hc = cfg["model"], cfg["fire_history"]
    interim = cfg["paths"]["interim"]
    end = hc["history_end_year"]
    train = importlib.import_module("placement.steps.06_train")

    grid = Grid(**json.loads((interim / "grid.json").read_text(encoding="utf-8")))
    cells = pd.read_parquet(interim / "cells.parquet")
    base = pd.read_parquet(interim / "features.parquet")
    ign = pd.read_parquet(interim / "fires_ignitions.parquet")
    clean = pd.read_parquet(interim / "fires_clean.parquet")
    every = pd.read_parquet(interim / "fires_all.parquet")

    hist_ign, target_ign = ign[ign.time.dt.year <= end], ign[ign.time.dt.year > end]
    hist_det = clean[clean.time.dt.year <= end]
    target_any = every[every.time.dt.year > end]
    print(
        f"history <= {end}: {len(hist_ign)} fire starts, {len(hist_det)} detections | "
        f"target > {end}: {len(target_ign)} fire starts",
        flush=True,
    )

    hist = history_features(cells, hist_ign, hist_det, hc["radii_m"])

    # Labels from the target period only.
    counts = events_per_cell(grid, target_ign)
    positive = cells.cell_id.isin(counts.index).to_numpy()
    burned_after = cells.cell_id.isin(events_per_cell(grid, target_any).index).to_numpy()
    n_pos = int(positive.sum())
    neg_idx = sample_negatives(
        cells, positive, burned_after, n_total=n_pos, seed=cfg["labels"]["seed"]
    )
    labelled = pd.concat(
        [
            cells.loc[positive, ["cell_id", "governorate"]].assign(label=1),
            cells.iloc[neg_idx][["cell_id", "governorate"]].assign(label=0),
        ],
        ignore_index=True,
    )
    labelled["n_events"] = labelled.cell_id.map(counts).fillna(0).astype(int)
    data = labelled.merge(base, on="cell_id").merge(hist, on="cell_id")
    print(
        f"labelled cells: {n_pos} fire / {len(neg_idx)} no-fire; "
        f"fire cells with 2+ starts: {(data.n_events >= 2).sum()}",
        flush=True,
    )

    base_cols = [c for c in base.columns if c != "cell_id"]
    hist_cols = [c for c in hist.columns if c != "cell_id"]
    y = data.label.to_numpy()
    folds = train._fold_labels(data.governorate, mc["merge_folds"]).to_numpy()
    weights = balanced_count_weights(y, data.n_events.to_numpy(), cap=hc["weight_cap"])

    variants: dict[str, tuple[list[str], np.ndarray | None]] = {
        "A_current": (base_cols, None),
        "B_history": (base_cols + hist_cols, None),
        "C_history_weighted": (base_cols + hist_cols, weights),
    }
    results: dict[str, Any] = {}
    for name in hc["models"]:
        for variant, (cols, w) in variants.items():
            X = data[cols]

            def factory(n: str = name, c: list[str] = cols) -> Any:
                return make_model(n, mc, c)

            cv = cross_validate(X, y, folds, factory, sample_weight=w)
            fold_auc = [m["roc_auc"] for m in cv.per_fold.values()]
            cap = capture_rate(y, cv.oof, AREA_SHARES)
            results[f"{name}/{variant}"] = {
                "mean_fold_roc_auc": float(np.nanmean(fold_auc)),
                "std_fold_roc_auc": float(np.nanstd(fold_auc)),
                "per_fold_roc_auc": {k: v["roc_auc"] for k, v in cv.per_fold.items()},
                "capture": {str(k): v for k, v in cap.items()},
            }
            print(
                f"  {name:13s} {variant:20s} ROC-AUC {np.nanmean(fold_auc):.3f} ± "
                f"{np.nanstd(fold_auc):.3f} | fires in riskiest 10/20/30% of land: "
                + " / ".join(f"{100 * cap[s]:.0f}%" for s in AREA_SHARES),
                flush=True,
            )

    write_json(
        cfg["paths"]["processed"] / "fire_history.json",
        {"config": hc, "n_pos": n_pos, "features_history": hist_cols, "results": results},
    )


if __name__ == "__main__":
    main()
