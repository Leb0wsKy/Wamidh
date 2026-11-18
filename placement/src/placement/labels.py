"""Negative sampling for the susceptibility model (CLAUDE.md §6.2 step 5).

Negatives are wildland cells with no cleaned detection, drawn with *proportional
allocation* across governorates: each governorate contributes negatives in proportion to
its number of eligible cells. The share of positives therefore still differs between
governorates, so the model can learn that some regions burn more than others.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from placement.grid import Grid


def allocate_proportional(available: pd.Series, total: int) -> pd.Series:
    """Split `total` across strata in proportion to `available`, never exceeding it.

    Largest-remainder rounding; capacity freed by capped strata is redistributed.
    """
    if total > available.sum():
        raise ValueError(f"cannot draw {total} from {available.sum()} available")
    alloc = pd.Series(0, index=available.index, dtype=np.int64)
    remaining = total
    while remaining > 0:
        room = available - alloc
        open_ = room > 0
        quota = remaining * available[open_] / available[open_].sum()
        add = np.minimum(np.floor(quota).astype(np.int64), room[open_])
        alloc[add.index] += add
        leftover = remaining - int(add.sum())
        # Units lost to rounding go to the largest fractional parts of this round.
        for key in (quota - np.floor(quota)).sort_values(ascending=False, kind="stable").index:
            if leftover == 0:
                break
            if alloc[key] < available[key]:
                alloc[key] += 1
                leftover -= 1
        remaining = total - int(alloc.sum())
    return alloc


def sample_negatives(
    cells: pd.DataFrame,
    positive: NDArray[np.bool_],
    excluded: NDArray[np.bool_],
    n_total: int,
    seed: int,
) -> NDArray[np.int64]:
    """Positional indices of negative cells, stratified by `cells['governorate']`."""
    eligible = ~positive & ~excluded
    gov = cells["governorate"].to_numpy()
    available = pd.Series(gov[eligible]).value_counts().sort_index()
    alloc = allocate_proportional(available, n_total)

    rng = np.random.default_rng(seed)
    picked: list[NDArray[np.int64]] = []
    for name, n in alloc.items():
        pool = np.flatnonzero(eligible & (gov == name))
        picked.append(rng.choice(pool, size=int(n), replace=False))
    return np.sort(np.concatenate(picked)).astype(np.int64)


def events_per_cell(grid: Grid, points: pd.DataFrame) -> pd.Series:
    """Number of points (columns x, y) falling in each grid cell, keyed by cell_id."""
    rows, cols = grid.index(points["x"].to_numpy(), points["y"].to_numpy())
    inside = rows >= 0
    ids = rows[inside] * grid.ncols + cols[inside]
    return pd.Series(ids).value_counts().sort_index()


def balanced_count_weights(
    label: NDArray[np.int_], count: NDArray[np.int_], cap: int
) -> NDArray[np.float64]:
    """Sample weights: positives weighted by their event count (capped), negatives 1, then
    rescaled so both classes carry equal total weight and the weights average to 1."""
    raw = np.where(label == 1, np.minimum(np.maximum(count, 1), cap), 1).astype(np.float64)
    half = len(label) / 2.0
    pos = label == 1
    raw[pos] *= half / raw[pos].sum()
    raw[~pos] *= half / raw[~pos].sum()
    return raw
