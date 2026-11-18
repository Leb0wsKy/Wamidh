import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from placement.model import (
    IsotonicCalibrator,
    block_folds,
    capture_rate,
    cross_validate,
    make_model,
    nested_spatial_cv,
    sample_params,
    score,
    spatial_folds,
)


def test_spatial_folds_merge_small_governorates() -> None:
    govs = pd.Series(["Tunis", "Ariana", "Jendouba", "Béja", "Tunis"])

    folds = spatial_folds(govs, merge={"Greater Tunis": ["Tunis", "Ariana"]})

    assert folds.tolist() == ["Greater Tunis", "Greater Tunis", "Jendouba", "Béja", "Greater Tunis"]


def _synthetic(n: int = 600, seed: int = 0) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"signal": rng.normal(size=n), "noise": rng.normal(size=n)})
    y = (X.signal + 0.5 * rng.normal(size=n) > 0).astype(int).to_numpy()
    groups = np.repeat(["a", "b", "c"], n // 3)
    return X, y, groups


def test_cross_validate_predicts_each_row_from_a_model_that_never_saw_its_group() -> None:
    X, y, groups = _synthetic()
    seen: list[set[str]] = []

    def factory() -> LogisticRegression:
        class Spy(LogisticRegression):
            def fit(self, X_, y_, **kw):  # type: ignore[no-untyped-def]
                seen.append(set(groups[X_.index]))
                return super().fit(X_, y_, **kw)

        return Spy()

    result = cross_validate(X, y, groups, factory)

    assert not np.isnan(result.oof).any()
    assert seen == [{"b", "c"}, {"a", "c"}, {"a", "b"}]
    assert set(result.per_fold) == {"a", "b", "c"}
    assert result.pooled["roc_auc"] > 0.85


def test_score_perfect_ranking() -> None:
    m = score(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]), threshold=0.5)

    assert m["roc_auc"] == 1.0 and m["pr_auc"] == 1.0
    assert m["precision"] == 1.0 and m["recall"] == 1.0


def test_isotonic_calibration_fixes_distorted_probabilities() -> None:
    rng = np.random.default_rng(1)
    p_true = rng.uniform(size=20000)
    y = (rng.uniform(size=20000) < p_true).astype(int)
    distorted = p_true**3  # a badly over-confident "no" model

    cal = IsotonicCalibrator().fit(distorted, y)
    fixed = cal.predict(distorted)

    def mean_gap(p: np.ndarray) -> float:
        bins = np.minimum((p * 10).astype(int), 9)
        return float(np.mean([abs(p[bins == b].mean() - y[bins == b].mean()) for b in range(10)]))

    assert mean_gap(fixed) < 0.03 < mean_gap(distorted)


def test_every_configured_model_learns_the_signal() -> None:
    X, y, groups = _synthetic()
    cfg = {
        "seed": 0,
        "logistic": {"C": 1.0},
        "random_forest": {"n_estimators": 50, "min_samples_leaf": 5},
        "lightgbm": {"n_estimators": 50, "learning_rate": 0.1, "num_leaves": 7},
        "xgboost": {"n_estimators": 50, "learning_rate": 0.1, "max_depth": 3},
    }
    for name in ["logistic", "random_forest", "lightgbm", "xgboost"]:
        result = cross_validate(X, y, groups, lambda n=name: make_model(n, cfg, list(X.columns)))
        assert result.pooled["roc_auc"] > 0.8, name


# --- hyperparameter tuning ---------------------------------------------------


def test_sample_params_draws_distinct_reproducible_combinations() -> None:
    space = {"a": [1, 2, 3], "b": ["x", "y"]}

    draws = sample_params(space, n_iter=4, seed=0)

    assert len(draws) == 4
    assert len({tuple(sorted(d.items())) for d in draws}) == 4
    assert all(d["a"] in space["a"] and d["b"] in space["b"] for d in draws)
    assert draws == sample_params(space, n_iter=4, seed=0)
    assert len(sample_params(space, n_iter=50, seed=0)) == 6  # capped at the full grid


def test_nested_cv_never_tunes_on_the_held_out_region() -> None:
    X, y, groups = _synthetic(n=400)
    groups = np.repeat(["a", "b", "c", "d"], 100)
    trained_on: list[set[str]] = []

    def spy_build(name, cfg, features):  # type: ignore[no-untyped-def]
        class Spy(LogisticRegression):
            def fit(self, X_, y_, **kw):  # type: ignore[no-untyped-def]
                trained_on.append(set(groups[X_.index]))
                return super().fit(X_, y_, **kw)

        return Spy(C=cfg["logistic"]["C"])

    cfg = {"seed": 0, "logistic": {"C": 1.0}}
    n_iter = 2
    result = nested_spatial_cv(
        X, y, groups, "logistic", cfg, {"C": [0.1, 1.0]}, n_iter=n_iter, seed=0, build=spy_build
    )

    # Per outer fold: n_iter settings x 3 inner folds, then one refit on the 3 training regions.
    per_outer = n_iter * 3 + 1
    for k, held_out in enumerate(["a", "b", "c", "d"]):
        chunk = trained_on[k * per_outer : (k + 1) * per_outer]
        assert all(held_out not in s for s in chunk)
        assert chunk[-1] == {"a", "b", "c", "d"} - {held_out}
    assert set(result.chosen) == {"a", "b", "c", "d"}
    assert not np.isnan(result.cv.oof).any()


def test_nested_cv_picks_the_clearly_better_setting() -> None:
    # XOR: depth-1 trees cannot see it, unlimited depth can.
    rng = np.random.default_rng(3)
    n = 900
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n)})
    y = ((X.a > 0) ^ (X.b > 0)).astype(int).to_numpy()
    groups = np.repeat(["g1", "g2", "g3"], n // 3)
    cfg = {"seed": 0, "random_forest": {"n_estimators": 50, "min_samples_leaf": 5}}

    result = nested_spatial_cv(
        X, y, groups, "random_forest", cfg, {"max_depth": [1, None]}, n_iter=2, seed=0
    )

    assert all(p["max_depth"] is None for p in result.chosen.values())
    assert result.cv.pooled["roc_auc"] > 0.9


# --- spatial blocks within one region ----------------------------------------


def test_block_folds_keep_each_block_in_a_single_fold() -> None:
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 50_000, size=2000)
    y = rng.uniform(0, 50_000, size=2000)

    folds = block_folds(x, y, block_m=10_000, n_folds=5, seed=1)

    block = (x // 10_000).astype(int) * 1000 + (y // 10_000).astype(int)
    per_block = pd.Series(folds).groupby(block).nunique()
    assert (per_block == 1).all()
    assert set(folds) == {0, 1, 2, 3, 4}
    assert np.array_equal(folds, block_folds(x, y, block_m=10_000, n_folds=5, seed=1))
    assert not np.array_equal(folds, block_folds(x, y, block_m=10_000, n_folds=5, seed=2))


# --- sample weights and capture rate ------------------------------------------


def test_cross_validate_passes_sample_weights_of_the_training_rows() -> None:
    X, y, groups = _synthetic(n=300)
    weights = np.arange(300, dtype=float)
    received: list[np.ndarray] = []

    class Spy(LogisticRegression):
        def fit(self, X_, y_, sample_weight=None):  # type: ignore[no-untyped-def]
            received.append(sample_weight)
            return super().fit(X_, y_, sample_weight=sample_weight)

    cross_validate(X, y, groups, Spy, sample_weight=weights)

    assert np.array_equal(received[0], weights[groups != "a"])


def test_capture_rate_share_of_fires_in_riskiest_share_of_land() -> None:
    # Negatives stand for the land; positives for fire starts.
    y = np.array([0, 0, 0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.9, 0.8, 0.95])

    cap = capture_rate(y, p, area_shares=[0.25, 0.5])

    # Riskiest 25% of land = scores >= 0.9 -> captures 1 of 2 fires; 50% (>= 0.3) -> both.
    assert cap == {0.25: 0.5, 0.5: 1.0}
