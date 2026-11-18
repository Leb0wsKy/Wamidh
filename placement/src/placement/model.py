"""Susceptibility models, spatial cross-validation, scoring and calibration."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from numpy.typing import NDArray
from sklearn.base import ClassifierMixin
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from xgboost import XGBClassifier

FloatArray = NDArray[np.float64]


def spatial_folds(governorates: pd.Series, merge: Mapping[str, Sequence[str]]) -> pd.Series:
    """Fold label per row: the governorate, or the merged group it belongs to."""
    lookup = {member: group for group, members in merge.items() for member in members}
    return governorates.map(lambda g: lookup.get(g, g))


def block_folds(
    x: FloatArray, y: FloatArray, block_m: float, n_folds: int, seed: int
) -> NDArray[np.int64]:
    """Spatial block CV inside one region: square blocks of `block_m`, each block assigned
    whole to one of `n_folds` folds at random, so neighbouring cells never straddle
    the train/test split within a block."""
    bx = np.floor(np.asarray(x) / block_m).astype(np.int64)
    by = np.floor(np.asarray(y) / block_m).astype(np.int64)
    blocks, block_of_row = np.unique(np.column_stack([bx, by]), axis=0, return_inverse=True)
    rng = np.random.default_rng(seed)
    fold_of_block = rng.permutation(len(blocks)) % n_folds
    return fold_of_block[block_of_row.ravel()].astype(np.int64)


def _log_distances(X: pd.DataFrame) -> pd.DataFrame:
    """Distances are heavily right-skewed; a linear model sees log(1 + d) instead."""
    X = X.copy()
    dist = [c for c in X.columns if c.startswith("dist_")]
    X[dist] = np.log1p(X[dist])
    return X


def make_model(name: str, cfg: dict[str, Any], features: list[str]) -> ClassifierMixin:
    seed = cfg["seed"]
    if name == "logistic":
        return Pipeline(
            [
                ("log_dist", FunctionTransformer(_log_distances)),
                ("scale", StandardScaler()),
                ("clf", LogisticRegression(C=cfg["logistic"]["C"], max_iter=5000)),
            ]
        )
    if name == "random_forest":
        rf = cfg["random_forest"]
        return RandomForestClassifier(
            n_estimators=rf["n_estimators"],
            min_samples_leaf=rf["min_samples_leaf"],
            max_depth=rf.get("max_depth"),
            max_features=rf.get("max_features", "sqrt"),
            n_jobs=-1,
            random_state=seed,
        )
    if name == "lightgbm":
        lg = cfg["lightgbm"]
        return LGBMClassifier(
            n_estimators=lg["n_estimators"],
            learning_rate=lg["learning_rate"],
            num_leaves=lg["num_leaves"],
            subsample=lg.get("subsample", 1.0),
            subsample_freq=1 if lg.get("subsample", 1.0) < 1.0 else 0,
            colsample_bytree=lg.get("colsample_bytree", 1.0),
            min_child_samples=lg.get("min_child_samples", 20),
            reg_lambda=lg.get("reg_lambda", 0.0),
            random_state=seed,
            verbose=-1,
        )
    if name == "xgboost":
        xg = cfg["xgboost"]
        return XGBClassifier(
            n_estimators=xg["n_estimators"],
            learning_rate=xg["learning_rate"],
            max_depth=xg["max_depth"],
            subsample=xg.get("subsample", 1.0),
            colsample_bytree=xg.get("colsample_bytree", 1.0),
            min_child_weight=xg.get("min_child_weight", 1.0),
            reg_lambda=xg.get("reg_lambda", 1.0),
            tree_method="hist",
            random_state=seed,
            n_jobs=-1,
        )
    raise ValueError(f"unknown model {name!r}")


def score(y: NDArray[np.int_], p: FloatArray, threshold: float) -> dict[str, float]:
    pred = (p >= threshold).astype(int)
    two_classes = len(np.unique(y)) == 2
    return {
        "roc_auc": float(roc_auc_score(y, p)) if two_classes else float("nan"),
        "pr_auc": float(average_precision_score(y, p)) if two_classes else float("nan"),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "brier": float(brier_score_loss(y, p)),
        "n": int(len(y)),
        "n_pos": int(np.sum(y)),
    }


@dataclass
class CVResult:
    oof: FloatArray
    per_fold: dict[str, dict[str, float]] = field(default_factory=dict)
    pooled: dict[str, float] = field(default_factory=dict)


def cross_validate(
    X: pd.DataFrame,
    y: NDArray[np.int_],
    groups: NDArray[Any],
    factory: Callable[[], ClassifierMixin],
    threshold: float = 0.5,
    sample_weight: FloatArray | None = None,
) -> CVResult:
    """Leave-one-group-out: every row is predicted by a model that never saw its group.

    `sample_weight` (optional) weights the training rows; test scores are unweighted.
    """
    oof = np.full(len(y), np.nan)
    result = CVResult(oof=oof)
    for g in pd.unique(groups):
        test = groups == g
        model = factory()
        if sample_weight is None:
            model.fit(X[~test], y[~test])
        else:
            model.fit(X[~test], y[~test], sample_weight=sample_weight[~test])
        oof[test] = model.predict_proba(X[test])[:, 1]
        result.per_fold[str(g)] = score(y[test], oof[test], threshold)
    result.pooled = score(y, oof, threshold)
    return result


def capture_rate(
    y: NDArray[np.int_], p: FloatArray, area_shares: Sequence[float]
) -> dict[float, float]:
    """Share of positives (fire starts) inside the riskiest `share` of the land.

    Negatives are a random sample of fire-free wildland, so they stand for the land: the
    threshold is the score of the k-th riskiest negative, k = ceil(share * n_negatives).
    """
    neg = np.sort(p[y == 0])[::-1]
    pos = p[y == 1]
    out = {}
    for share in area_shares:
        k = max(1, int(np.ceil(share * len(neg))))
        out[share] = float(np.mean(pos >= neg[k - 1]))
    return out


class IsotonicCalibrator:
    """Monotone map from model scores to observed frequencies (fit on out-of-fold scores)."""

    def __init__(self) -> None:
        self._iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")

    def fit(self, p: FloatArray, y: NDArray[np.int_]) -> IsotonicCalibrator:
        self._iso.fit(p, y)
        return self

    def predict(self, p: FloatArray) -> FloatArray:
        return np.asarray(self._iso.predict(p), dtype=np.float64)


# --- hyperparameter tuning ---------------------------------------------------

Builder = Callable[[str, dict[str, Any], list[str]], ClassifierMixin]


def sample_params(
    space: Mapping[str, Sequence[Any]], n_iter: int, seed: int
) -> list[dict[str, Any]]:
    """Up to `n_iter` distinct combinations drawn at random from the grid `space`."""
    keys = list(space)
    grid = list(itertools.product(*(space[k] for k in keys)))
    rng = np.random.default_rng(seed)
    picks = rng.permutation(len(grid))[: min(n_iter, len(grid))]
    return [dict(zip(keys, grid[i], strict=True)) for i in picks]


def _with_params(cfg: dict[str, Any], name: str, params: dict[str, Any]) -> dict[str, Any]:
    return {**cfg, name: {**cfg.get(name, {}), **params}}


@dataclass
class TuneResult:
    best_params: dict[str, Any]
    best_score: float
    trials: list[dict[str, Any]]  # params + mean inner-fold ROC-AUC, in search order


def tune_spatial(
    X: pd.DataFrame,
    y: NDArray[np.int_],
    groups: NDArray[Any],
    name: str,
    cfg: dict[str, Any],
    space: Mapping[str, Sequence[Any]],
    n_iter: int,
    seed: int,
    build: Builder = make_model,
) -> TuneResult:
    """Random search scored by leave-one-group-out ROC-AUC (mean over folds)."""
    features = list(X.columns)
    trials = []
    for params in sample_params(space, n_iter, seed):
        trial_cfg = _with_params(cfg, name, params)

        def factory(c: dict[str, Any] = trial_cfg) -> ClassifierMixin:
            return build(name, c, features)

        cv = cross_validate(X, y, groups, factory)
        mean_auc = float(np.nanmean([m["roc_auc"] for m in cv.per_fold.values()]))
        trials.append({**params, "mean_fold_roc_auc": mean_auc})
    best = max(trials, key=lambda t: t["mean_fold_roc_auc"])
    best_params = {k: v for k, v in best.items() if k != "mean_fold_roc_auc"}
    return TuneResult(best_params, best["mean_fold_roc_auc"], trials)


@dataclass
class NestedResult:
    cv: CVResult
    chosen: dict[str, dict[str, Any]]  # outer fold -> params picked by the inner search
    inner_score: dict[str, float]  # outer fold -> best inner-CV ROC-AUC


def nested_spatial_cv(
    X: pd.DataFrame,
    y: NDArray[np.int_],
    groups: NDArray[Any],
    name: str,
    cfg: dict[str, Any],
    space: Mapping[str, Sequence[Any]],
    n_iter: int,
    seed: int,
    build: Builder = make_model,
    threshold: float = 0.5,
    progress: Callable[[str], None] | None = None,
) -> NestedResult:
    """Honest estimate of a *tuned* model: each outer region is scored by a model whose
    hyperparameters were chosen by spatial CV on the other regions only."""
    features = list(X.columns)
    oof = np.full(len(y), np.nan)
    result = NestedResult(cv=CVResult(oof=oof), chosen={}, inner_score={})
    for g in pd.unique(groups):
        test = groups == g
        tuned = tune_spatial(
            X[~test], y[~test], groups[~test], name, cfg, space, n_iter, seed, build
        )
        model = build(name, _with_params(cfg, name, tuned.best_params), features)
        model.fit(X[~test], y[~test])
        oof[test] = model.predict_proba(X[test])[:, 1]
        fold_scores = score(y[test], oof[test], threshold)
        result.cv.per_fold[str(g)] = fold_scores
        result.chosen[str(g)] = tuned.best_params
        result.inner_score[str(g)] = tuned.best_score
        if progress:
            progress(
                f"{name} | held out {g}: inner ROC-AUC {tuned.best_score:.3f}, "
                f"outer ROC-AUC {fold_scores['roc_auc']:.3f}, params {tuned.best_params}"
            )
    result.cv.pooled = score(y, oof, threshold)
    return result
