"""Step 06 — train and evaluate the ignition-susceptibility models.

Training table: labels from the target years + static features + fire history from the
training window (see step 05 and placement.history).

1. Spatial cross-validation (leave one governorate out) for each model -> honest scores.
2. The same models under a random K-fold split -> shows how much spatial leakage inflates
   scores (reported, never used for selection).
3. Best model by mean spatial-fold score; isotonic calibration fitted on its out-of-fold
   predictions; final model refitted on all labelled cells.
4. Explainability: permutation importance on held-out folds (best model) and SHAP values
   (best tree model).

Outputs (data/processed/): model.joblib, train_metrics.json, oof_predictions.parquet,
shap_values.parquet, permutation_importance.csv.
"""

from __future__ import annotations

import logging
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.inspection import permutation_importance
from sklearn.model_selection import StratifiedKFold

from placement.io import normalise_name, step_main, write_json
from placement.model import IsotonicCalibrator, cross_validate, make_model, score, spatial_folds

log = logging.getLogger("placement.train")


def load_training_table(interim: Any) -> pd.DataFrame:
    """Labels (target years) + static features + fire history from the training window."""
    labels = pd.read_parquet(interim / "labels.parquet")
    feats = pd.read_parquet(interim / "features.parquet")
    hist = pd.read_parquet(interim / "history_train.parquet")
    return labels.merge(feats, on="cell_id", validate="one_to_one").merge(
        hist, on="cell_id", validate="one_to_one"
    )


def _fold_labels(gov: pd.Series, merge_cfg: dict[str, list[str]]) -> pd.Series:
    by_norm = {normalise_name(g): g for g in gov.unique()}
    merge = {
        group: [by_norm[normalise_name(m)] for m in members if normalise_name(m) in by_norm]
        for group, members in merge_cfg.items()
    }
    return spatial_folds(gov, merge)


def _calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 10) -> list[dict[str, float]]:
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return [
        {
            "bin": b,
            "mean_pred": float(p[idx == b].mean()),
            "frac_pos": float(y[idx == b].mean()),
            "n": int((idx == b).sum()),
        }
        for b in range(bins)
        if (idx == b).any()
    ]


def run(cfg: dict[str, Any]) -> None:
    interim, processed = cfg["paths"]["interim"], cfg["paths"]["processed"]
    processed.mkdir(parents=True, exist_ok=True)
    mc = cfg["model"]

    data = load_training_table(interim)
    features = [c for c in data.columns if c not in ("cell_id", "governorate", "label")]
    X, y = data[features], data["label"].to_numpy()
    folds = _fold_labels(data["governorate"], mc["merge_folds"]).to_numpy()
    rng_folds = np.empty(len(y), dtype=object)
    skf = StratifiedKFold(mc["random_cv_folds"], shuffle=True, random_state=mc["seed"])
    for k, (_, test) in enumerate(skf.split(X, y)):
        rng_folds[test] = f"random_{k}"

    metrics: dict[str, Any] = {
        "n_cells": len(y),
        "n_pos": int(y.sum()),
        "features": features,
        "folds": pd.Series(folds).value_counts().to_dict(),
        "models": {},
    }
    oof = pd.DataFrame({"cell_id": data.cell_id, "label": y, "fold": folds})

    for name in mc["models"]:

        def factory(n: str = name) -> Any:
            return make_model(n, mc, features)

        spatial = cross_validate(X, y, folds, factory, mc["threshold"])
        random = cross_validate(X, y, rng_folds, factory, mc["threshold"])
        fold_auc = [m["roc_auc"] for m in spatial.per_fold.values()]
        fold_pr = [m["pr_auc"] for m in spatial.per_fold.values()]
        metrics["models"][name] = {
            "spatial_cv": {
                "mean_fold_roc_auc": float(np.nanmean(fold_auc)),
                "std_fold_roc_auc": float(np.nanstd(fold_auc)),
                "mean_fold_pr_auc": float(np.nanmean(fold_pr)),
                "pooled": spatial.pooled,
                "per_fold": spatial.per_fold,
            },
            "random_cv": {"pooled": random.pooled},
        }
        oof[f"oof_{name}"] = spatial.oof
        log.info(
            "%-13s spatial ROC-AUC %.3f ± %.3f | random-split ROC-AUC %.3f",
            name,
            np.nanmean(fold_auc),
            np.nanstd(fold_auc),
            random.pooled["roc_auc"],
        )

    key = f"mean_fold_{mc['select_by']}"
    best = max(mc["models"], key=lambda n: metrics["models"][n]["spatial_cv"][key])
    metrics["best_model"] = best
    log.info("best model by %s: %s", key, best)

    # Calibration on out-of-fold scores, so it is not fitted on in-sample predictions.
    raw = oof[f"oof_{best}"].to_numpy()
    calibrator = IsotonicCalibrator().fit(raw, y)
    cal = calibrator.predict(raw)
    oof["oof_best_calibrated"] = cal
    metrics["calibration"] = {
        "note": "isotonic fitted on spatial out-of-fold scores; evaluated in-sample on them",
        "brier_raw": float(np.mean((raw - y) ** 2)),
        "brier_calibrated": float(np.mean((cal - y) ** 2)),
        "curve_raw": _calibration_table(y, raw),
        "curve_calibrated": _calibration_table(y, cal),
        "scores_at_threshold": score(y, cal, mc["threshold"]),
    }
    oof.to_parquet(processed / "oof_predictions.parquet")

    final = make_model(best, mc, features).fit(X, y)
    joblib.dump(
        {"model": final, "calibrator": calibrator, "features": features, "name": best},
        processed / "model.joblib",
    )

    # Permutation importance: drop in ROC-AUC on each held-out fold, averaged.
    perm = []
    for g in pd.unique(folds):
        test = folds == g
        if len(np.unique(y[test])) < 2:
            continue
        m = make_model(best, mc, features).fit(X[~test], y[~test])
        r = permutation_importance(
            m,
            X[test],
            y[test],
            scoring="roc_auc",
            n_repeats=mc["permutation_repeats"],
            random_state=mc["seed"],
        )
        perm.append(pd.Series(r.importances_mean, index=features, name=str(g)))
    perm_df = pd.concat(perm, axis=1)
    perm_df["mean"] = perm_df.mean(axis=1)
    perm_df = perm_df.sort_values("mean", ascending=False)
    perm_df.to_csv(processed / "permutation_importance.csv")
    metrics["permutation_importance_top"] = perm_df["mean"].head(8).round(4).to_dict()

    # SHAP on the best tree model (exact TreeSHAP), refitted on all data.
    tree_models = [n for n in mc["models"] if n != "logistic"]
    shap_name = max(tree_models, key=lambda n: metrics["models"][n]["spatial_cv"][key])
    tree = final if shap_name == best else make_model(shap_name, mc, features).fit(X, y)
    values = shap.TreeExplainer(tree).shap_values(X)
    if isinstance(values, list):  # older shap: one array per class
        values = values[1]
    if values.ndim == 3:  # (n, features, classes)
        values = values[:, :, 1]
    shap_df = pd.DataFrame(values, columns=features)
    shap_df.insert(0, "cell_id", data.cell_id.to_numpy())
    shap_df.to_parquet(processed / "shap_values.parquet")
    metrics["shap_model"] = shap_name
    metrics["shap_mean_abs_top"] = (
        shap_df[features].abs().mean().sort_values(ascending=False).head(8).round(4).to_dict()
    )

    write_json(processed / "train_metrics.json", metrics)
    log.info("permutation importance (top): %s", metrics["permutation_importance_top"])
    log.info("SHAP mean |value| (%s, top): %s", shap_name, metrics["shap_mean_abs_top"])
    log.info(
        "calibration Brier %.4f -> %.4f",
        metrics["calibration"]["brier_raw"],
        metrics["calibration"]["brier_calibrated"],
    )


if __name__ == "__main__":
    step_main(run, "Step 06 - train susceptibility models")
