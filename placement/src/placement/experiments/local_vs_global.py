"""Does a model trained only on the pilot governorate beat one trained on all of the north?

    python -m placement.experiments.local_vs_global --config config/pilot_kroumirie.yaml

The pilot region's cells are split into spatial blocks (block CV). For each held-out block
fold, three approaches predict the same cells:

  local     trained on the region's other blocks only
  global    trained on every other governorate + the region's other blocks
  transfer  trained on every other governorate, nothing from the region

Output: data/processed/local_vs_global.json
"""

from __future__ import annotations

import argparse
import importlib
from typing import Any

import numpy as np
import pandas as pd

from placement.config import load_config
from placement.io import normalise_name, write_json
from placement.model import block_folds, make_model, score

APPROACHES = ["local", "global", "transfer"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Local vs global model comparison")
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)
    mc, ec = cfg["model"], cfg["local_experiment"]
    interim = cfg["paths"]["interim"]
    train = importlib.import_module("placement.steps.06_train")

    data = train.load_training_table(interim)
    xy = pd.read_parquet(interim / "cells.parquet")[["cell_id", "x", "y"]]
    data = data.merge(xy, on="cell_id", validate="one_to_one")
    features = [c for c in data.columns if c not in ("cell_id", "governorate", "label", "x", "y")]
    in_region = (data.governorate.map(normalise_name) == normalise_name(ec["region"])).to_numpy()
    X, y = data[features], data["label"].to_numpy()
    Xr, yr = X[in_region], y[in_region]
    xr, yr_coord = data.x[in_region].to_numpy(), data.y[in_region].to_numpy()

    print(
        f"{ec['region']}: {in_region.sum()} labelled cells ({yr.sum()} fires); "
        f"other regions: {(~in_region).sum()} cells",
        flush=True,
    )

    results: dict[str, Any] = {name: {a: [] for a in APPROACHES} for name in ec["models"]}
    for rep in range(ec["repeats"]):
        folds = block_folds(xr, yr_coord, ec["block_m"], ec["n_folds"], seed=mc["seed"] + rep)
        for name in ec["models"]:
            preds = {a: np.full(len(yr), np.nan) for a in APPROACHES}
            transfer = make_model(name, mc, features).fit(X[~in_region], y[~in_region])
            for k in range(ec["n_folds"]):
                test = folds == k
                local = make_model(name, mc, features).fit(Xr[~test], yr[~test])
                glob = make_model(name, mc, features).fit(
                    pd.concat([X[~in_region], Xr[~test]]),
                    np.concatenate([y[~in_region], yr[~test]]),
                )
                preds["local"][test] = local.predict_proba(Xr[test])[:, 1]
                preds["global"][test] = glob.predict_proba(Xr[test])[:, 1]
                preds["transfer"][test] = transfer.predict_proba(Xr[test])[:, 1]
            line = []
            for a in APPROACHES:
                fold_auc = [
                    score(yr[folds == k], preds[a][folds == k], 0.5)["roc_auc"]
                    for k in range(ec["n_folds"])
                ]
                results[name][a].append(float(np.mean(fold_auc)))
                line.append(f"{a} {np.mean(fold_auc):.3f}")
            n_blocks = len(
                np.unique(np.column_stack([xr // ec["block_m"], yr_coord // ec["block_m"]]), axis=0)
            )
            print(
                f"  repeat {rep + 1} | {name:13s} | "
                + " | ".join(line)
                + f"   ({n_blocks} blocks)",
                flush=True,
            )

    summary = {
        name: {
            a: {"mean_roc_auc": float(np.mean(v)), "per_repeat": v} for a, v in per_model.items()
        }
        for name, per_model in results.items()
    }
    write_json(
        cfg["paths"]["processed"] / "local_vs_global.json",
        {"config": ec, "n_region_cells": int(in_region.sum()), "results": summary},
    )
    print("\n=== mean ROC-AUC on held-out Jendouba blocks (average of repeats) ===")
    print(f"{'model':15s}" + "".join(f"{a:>10s}" for a in APPROACHES))
    for name, per_model in summary.items():
        print(f"{name:15s}" + "".join(f"{per_model[a]['mean_roc_auc']:>10.3f}" for a in APPROACHES))


if __name__ == "__main__":
    main()
