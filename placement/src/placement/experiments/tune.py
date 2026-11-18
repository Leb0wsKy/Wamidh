"""Hyperparameter tuning experiment (nested spatial cross-validation).

    python -m placement.experiments.tune --config config/pilot_kroumirie.yaml --model lightgbm

1. Nested spatial CV -> the honest score of the *tuned* model (compare with step 06's
   untuned score from train_metrics.json).
2. Plain spatial random search on all labelled cells -> the settings to put in the config
   if tuning is worth it.

Output: data/processed/tuning_<model>.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import time

import numpy as np

from placement.config import load_config
from placement.io import write_json
from placement.model import nested_spatial_cv, tune_spatial


def main() -> None:
    parser = argparse.ArgumentParser(description="Nested spatial CV hyperparameter tuning")
    parser.add_argument("--config", required=True)
    parser.add_argument("--model", required=True, choices=["random_forest", "lightgbm", "xgboost"])
    parser.add_argument("--n-iter", type=int, help="override tuning.n_iter")
    args = parser.parse_args()

    cfg = load_config(args.config)
    mc, tc = cfg["model"], cfg["tuning"]
    n_iter = args.n_iter or tc["n_iter"]
    space = tc["space"][args.model]
    train = importlib.import_module("placement.steps.06_train")

    data = train.load_training_table(cfg["paths"]["interim"])
    features = [c for c in data.columns if c not in ("cell_id", "governorate", "label")]
    X, y = data[features], data["label"].to_numpy()
    groups = train._fold_labels(data["governorate"], mc["merge_folds"]).to_numpy()

    print(f"Tuning {args.model}: {n_iter} settings x {len(set(groups))} outer regions", flush=True)
    t0 = time.perf_counter()
    nested = nested_spatial_cv(
        X,
        y,
        groups,
        args.model,
        mc,
        space,
        n_iter,
        tc["seed"],
        threshold=mc["threshold"],
        progress=lambda msg: print("  " + msg, flush=True),
    )
    fold_auc = [m["roc_auc"] for m in nested.cv.per_fold.values()]
    tuned_mean = float(np.nanmean(fold_auc))
    print(f"Nested CV done in {time.perf_counter() - t0:.0f} s", flush=True)

    print("Choosing final settings on all regions ...", flush=True)
    final = tune_spatial(X, y, groups, args.model, mc, space, n_iter, tc["seed"])

    baseline_path = cfg["paths"]["processed"] / "train_metrics.json"
    baseline = None
    if baseline_path.exists():
        base = json.loads(baseline_path.read_text(encoding="utf-8"))["models"].get(args.model)
        baseline = base["spatial_cv"]["mean_fold_roc_auc"] if base else None

    out = {
        "model": args.model,
        "n_iter": n_iter,
        "untuned_mean_fold_roc_auc": baseline,
        "tuned_mean_fold_roc_auc": tuned_mean,
        "tuned_std_fold_roc_auc": float(np.nanstd(fold_auc)),
        "tuned_pooled": nested.cv.pooled,
        "per_fold": nested.cv.per_fold,
        "chosen_per_fold": nested.chosen,
        "inner_score_per_fold": nested.inner_score,
        "final_params": final.best_params,
        "final_inner_mean_fold_roc_auc": final.best_score,
        "final_trials": final.trials,
    }
    write_json(cfg["paths"]["processed"] / f"tuning_{args.model}.json", out)

    print("\n=== result ===")
    if baseline is not None:
        print(f"untuned (step 06)  : {baseline:.3f}")
    print(f"tuned (nested CV)  : {tuned_mean:.3f} ± {np.nanstd(fold_auc):.3f}")
    print(f"final settings     : {final.best_params}")


if __name__ == "__main__":
    main()
