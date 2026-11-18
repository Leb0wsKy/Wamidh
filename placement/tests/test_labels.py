import numpy as np
import pandas as pd
import pytest

from placement.grid import Grid
from placement.labels import (
    allocate_proportional,
    balanced_count_weights,
    events_per_cell,
    sample_negatives,
)


def test_allocation_is_proportional_and_sums_exactly() -> None:
    alloc = allocate_proportional(pd.Series({"A": 600, "B": 300, "C": 100}), total=7)

    assert alloc.sum() == 7
    assert alloc.to_dict() == {"A": 4, "B": 2, "C": 1}


def test_allocation_never_exceeds_available() -> None:
    alloc = allocate_proportional(pd.Series({"A": 2, "B": 1000}), total=900)

    assert alloc["A"] <= 2
    assert alloc.sum() == 900


def _cells() -> pd.DataFrame:
    gov = ["A"] * 60 + ["B"] * 30 + ["C"] * 10
    return pd.DataFrame({"governorate": gov})


def test_negatives_exclude_positive_and_burned_cells() -> None:
    cells = _cells()
    positive = np.zeros(100, dtype=bool)
    positive[:5] = True
    burned = np.zeros(100, dtype=bool)
    burned[5:10] = True

    idx = sample_negatives(cells, positive, burned, n_total=20, seed=1)

    assert len(idx) == len(set(idx)) == 20
    assert not positive[idx].any() and not burned[idx].any()


def test_negatives_are_stratified_by_governorate_and_reproducible() -> None:
    cells = _cells()
    none = np.zeros(100, dtype=bool)

    idx = sample_negatives(cells, none, none, n_total=10, seed=7)

    assert cells.loc[idx, "governorate"].value_counts().to_dict() == {"A": 6, "B": 3, "C": 1}
    assert np.array_equal(idx, sample_negatives(cells, none, none, n_total=10, seed=7))


def test_events_per_cell_counts_points_in_each_grid_cell() -> None:
    grid = Grid(x0=0, y0=1000, cell=500, nrows=2, ncols=2)
    pts = pd.DataFrame({"x": [10.0, 20.0, 600.0, 5000.0], "y": [990.0, 980.0, 100.0, 0.0]})

    counts = events_per_cell(grid, pts)

    # Two points in cell (0,0) -> id 0, one in (1,1) -> id 3, one outside the grid ignored.
    assert counts.to_dict() == {0: 2, 3: 1}


def test_balanced_weights_cap_counts_and_equalise_class_totals() -> None:
    label = np.array([1, 1, 1, 0, 0, 0, 0])
    count = np.array([1, 3, 12, 0, 0, 0, 0])

    w = balanced_count_weights(label, count, cap=5)

    np.testing.assert_allclose(w[:3] / w[0], [1, 3, 5])  # capped at 5
    assert w[label == 1].sum() == pytest.approx(w[label == 0].sum())
    assert w.sum() == pytest.approx(len(label))
