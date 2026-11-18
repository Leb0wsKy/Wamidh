"""Node and gateway placement as coverage problems.

Nodes: greedy weighted maximum coverage. The objective (total risk within detection range
of at least one node) is monotone submodular, so greedy selection reaches at least
1 - 1/e (~63%) of the optimum (Nemhauser, Wolsey & Fisher, 1978). Lazy evaluation (CELF,
Leskovec et al., 2007) gives the same answer as plain greedy, much faster.

Gateways: greedy set cover over a node-visibility matrix (ln(n)-approximation).

All coordinates are metric (EPSG:32632), x = east, y = north.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy import sparse
from scipy.spatial import cKDTree


@dataclass
class GreedyResult:
    selected: list[int]
    cumulative_covered: NDArray[np.float64]  # objective after each pick


@dataclass
class SetCoverResult:
    selected: list[int]
    uncovered: list[int] = field(default_factory=list)


def directional_radius(
    bearing_deg: NDArray[np.float64],
    radius_m: float,
    wind_from_deg: float,
    downwind_factor: float,
) -> NDArray[np.float64]:
    """Effective detection radius towards a target at `bearing_deg` from the node.

    Full radius towards the upwind side (where smoke comes from), `downwind_factor * radius`
    on the downwind side, smooth cosine blend in between.
    """
    delta = np.deg2rad(bearing_deg - wind_from_deg)
    blend = (1.0 + np.cos(delta)) / 2.0  # 1 upwind, 0 downwind
    return radius_m * (downwind_factor + (1.0 - downwind_factor) * blend)


def coverage_matrix(
    candidates_xy: NDArray[np.float64],
    targets_xy: NDArray[np.float64],
    radius_m: float,
    wind_from_deg: float | None = None,
    downwind_factor: float = 1.0,
) -> sparse.csr_matrix:
    """Boolean (n_candidates x n_targets) matrix: can candidate i detect a fire at target j."""
    tree = cKDTree(targets_xy)
    neighbours = tree.query_ball_point(candidates_xy, r=radius_m + 1e-9)

    rows: list[int] = []
    cols: list[int] = []
    for i, idx in enumerate(neighbours):
        if not idx:
            continue
        idx_arr = np.asarray(idx)
        if wind_from_deg is not None and downwind_factor < 1.0:
            d = targets_xy[idx_arr] - candidates_xy[i]
            dist = np.hypot(d[:, 0], d[:, 1])
            bearing = np.rad2deg(np.arctan2(d[:, 0], d[:, 1])) % 360.0
            r_eff = directional_radius(bearing, radius_m, wind_from_deg, downwind_factor)
            idx_arr = idx_arr[dist <= r_eff + 1e-9]
        rows.extend([i] * len(idx_arr))
        cols.extend(idx_arr.tolist())

    data = np.ones(len(rows), dtype=bool)
    shape = (len(candidates_xy), len(targets_xy))
    return sparse.csr_matrix((data, (rows, cols)), shape=shape)


def greedy_max_coverage(
    coverage: sparse.csr_matrix,
    weights: NDArray[np.float64],
    k: int,
    candidates_xy: NDArray[np.float64] | None = None,
    min_spacing_m: float = 0.0,
) -> GreedyResult:
    """Pick up to k rows of `coverage` maximising the total weight of covered columns.

    Stops early when no candidate adds any weight. Ties go to the lowest index.
    With `min_spacing_m` > 0, candidates closer than that to a chosen node are skipped
    (one node per hotspot instead of several packed on the same one).
    """
    coverage = sparse.csr_matrix(coverage, dtype=bool)
    weights = np.asarray(weights, dtype=np.float64)
    covered = np.zeros(coverage.shape[1], dtype=bool)
    blocked = np.zeros(coverage.shape[0], dtype=bool)
    tree = cKDTree(candidates_xy) if candidates_xy is not None and min_spacing_m > 0 else None

    def gain(i: int) -> float:
        cols = coverage.indices[coverage.indptr[i] : coverage.indptr[i + 1]]
        return float(weights[cols[~covered[cols]]].sum())

    # Max-heap of (-gain, index, round the gain was computed in).
    heap = [(-gain(i), i, 0) for i in range(coverage.shape[0])]
    heapq.heapify(heap)

    selected: list[int] = []
    totals: list[float] = []
    total = 0.0
    while heap and len(selected) < k:
        neg_g, i, computed_at = heapq.heappop(heap)
        if blocked[i]:
            continue
        if computed_at != len(selected):
            heapq.heappush(heap, (-gain(i), i, len(selected)))
            continue
        if -neg_g <= 0.0:
            break
        selected.append(i)
        covered[coverage.indices[coverage.indptr[i] : coverage.indptr[i + 1]]] = True
        if tree is not None:
            blocked[tree.query_ball_point(tree.data[i], r=min_spacing_m)] = True
        total += -neg_g
        totals.append(total)

    return GreedyResult(selected=selected, cumulative_covered=np.asarray(totals))


def greedy_set_cover(visibility: sparse.csr_matrix) -> SetCoverResult:
    """Fewest rows (gateways) such that every coverable column (node) is seen by one.

    Columns no row can cover are returned in `uncovered` rather than raising, so the
    pipeline can report nodes without radio line of sight.
    """
    visibility = sparse.csr_matrix(visibility, dtype=bool)
    coverable = np.asarray(visibility.sum(axis=0)).ravel() > 0
    result = greedy_max_coverage(visibility, np.ones(visibility.shape[1]), k=visibility.shape[0])
    return SetCoverResult(selected=result.selected, uncovered=np.flatnonzero(~coverable).tolist())


def wind_from_direction(u: float, v: float) -> float:
    """Meteorological direction (degrees clockwise from north) the wind blows FROM,
    given its eastward (u) and northward (v) components."""
    return float(np.rad2deg(np.arctan2(-u, -v)) % 360.0)


def random_baseline(
    coverage: sparse.csr_matrix, weights: NDArray[np.float64], n: int, repeats: int, seed: int
) -> dict[str, float]:
    """Covered weight when `n` candidates are chosen uniformly at random (mean, std)."""
    coverage = sparse.csr_matrix(coverage, dtype=bool)
    rng = np.random.default_rng(seed)
    totals = []
    for _ in range(repeats):
        picks = rng.choice(coverage.shape[0], size=min(n, coverage.shape[0]), replace=False)
        covered = np.zeros(coverage.shape[1], dtype=bool)
        covered[coverage[picks].indices] = True
        totals.append(float(weights[covered].sum()))
    return {"mean": float(np.mean(totals)), "std": float(np.std(totals))}
