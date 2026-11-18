"""Arrival time of a fire from one ignition cell: minimum travel time over a 16-neighbour grid
(Finney 2002), with rates of spread from fuel, slope and wind (ADR 0004)."""

from __future__ import annotations

import math
import weakref
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

from wamidh_spread.landscape import Landscape

# 16 neighbours: the 8 adjacent cells and the 8 knight moves. (row step, column step).
OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1),
    (-2, 1), (-1, 2), (1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1),
)  # fmt: skip
# Direction of travel of each offset, degrees from north, clockwise (row step points south).
AZIMUTHS = np.array([(math.degrees(math.atan2(dj, -di)) + 360) % 360 for di, dj in OFFSETS])
MPH_PER_MS = 2.23694
KMH_PER_MS = 3.6


@dataclass(frozen=True)
class Physics:
    midflame_factor: float
    max_length_to_breadth: float
    upslope_coeff: float
    downslope_coeff: float
    horizon_limit_min: float
    # Rate grows like ISI^c in the FBP System (ROS = a (1 - e^(-b ISI))^c, c ~ 1.5-2 for
    # forest types): the wind multiplier is raised to this power. 1 = ISI alone.
    wind_exponent: float = 1.0


def length_to_breadth(midflame_mph: float, cap: float = 8.0) -> float:
    """Fire ellipse length-to-breadth ratio from the midflame wind (Anderson 1983)."""
    u = max(midflame_mph, 0.0)
    lb = 0.936 * math.exp(0.2566 * u) + 0.461 * math.exp(-0.1548 * u) - 0.397
    return float(min(max(lb, 1.0), cap))


def wind_factors(wind_from_deg: float, wind_ms: float, phys: Physics) -> NDArray[np.float64]:
    """Rate multiplier for each of the 16 directions: the head runs downwind at
    exp(0.05039 * U10 km/h) ^ wind_exponent (FBP ISI wind function, Van Wagner 1987, with the
    curvature of the FBP rate-ISI curves), the flanks and back
    follow an ellipse with the ignition at its rear focus."""
    head = math.exp(0.05039 * max(wind_ms, 0.0) * KMH_PER_MS * phys.wind_exponent)
    lb = length_to_breadth(wind_ms * phys.midflame_factor * MPH_PER_MS, phys.max_length_to_breadth)
    e = math.sqrt(1 - 1 / lb**2)
    heading = (wind_from_deg + 180) % 360
    rel = np.radians(AZIMUTHS - heading)
    return np.asarray(head * (1 - e) / (1 - e * np.cos(rel)), dtype=np.float64)


def _crossed(di: int, dj: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """The two cells a knight move (di, dj) passes through, relative to its start."""
    if abs(di) == 2:
        return (di // 2, 0), (di // 2, dj)
    return (0, dj // 2), (di, dj // 2)


@dataclass(frozen=True)
class _Edges:
    """The grid's edges, sorted by source cell (CSR order), with what does not change between
    ensemble members precomputed: distance and the fuel x slope rate."""

    indptr: NDArray[np.int64]
    dst: NDArray[np.int64]
    offset: NDArray[np.int64]  # which of the 16 directions
    dist_m: NDArray[np.float64]
    rate: NDArray[np.float64]  # m/min before wind and the fuel multiplier


# Edges per landscape and physics. Keyed by id but checked through a weak reference: Python
# reuses the id of a freed landscape, and a stale entry would silently use the wrong terrain.
_EDGES: dict[tuple[int, Physics], tuple[weakref.ref[Landscape], _Edges]] = {}


def _edges(ls: Landscape, phys: Physics) -> _Edges:
    key = (id(ls), phys)
    hit = _EDGES.get(key)
    if hit is not None and hit[0]() is ls:
        return hit[1]
    for stale in [key for key, (ref, _) in _EDGES.items() if ref() is None]:
        del _EDGES[stale]
    rows, cols = ls.rows, ls.cols
    ii, jj = np.meshgrid(np.arange(rows), np.arange(cols), indexing="ij")
    src_all, dst_all, off_all, dist_all, rate_all = [], [], [], [], []
    ros = ls.ros.ravel()
    slope = ls.slope_deg.ravel()
    upslope = ls.upslope_az_deg.ravel()
    for k, (di, dj) in enumerate(OFFSETS):
        ti, tj = ii + di, jj + dj
        ok = (ti >= 0) & (ti < rows) & (tj >= 0) & (tj < cols)
        src = (ii * cols + jj)[ok]
        dst = (ti * cols + tj)[ok]
        base = (ros[src] + ros[dst]) / 2
        burn = (ros[src] > 0) & (ros[dst] > 0)
        if abs(di) + abs(dj) == 3:
            # A knight move crosses two cells on its way; both must burn, or the fire would
            # jump a one-cell river or road.
            for ci, cj in _crossed(di, dj):
                mid = np.clip(ii + ci, 0, rows - 1) * cols + np.clip(jj + cj, 0, cols - 1)
                burn &= ros[mid[ok]] > 0
        src, dst, base = src[burn], dst[burn], base[burn]
        along = slope[src] * np.cos(np.radians(AZIMUTHS[k] - upslope[src]))
        coeff = np.where(along > 0, phys.upslope_coeff, phys.downslope_coeff)
        src_all.append(src)
        dst_all.append(dst)
        off_all.append(np.full(src.size, k))
        dist_all.append(np.full(src.size, ls.cell_m * math.hypot(di, dj)))
        rate_all.append(base * np.exp(coeff * along))
    src = np.concatenate(src_all)
    order = np.argsort(src, kind="stable")
    src = src[order]
    indptr = np.zeros(ls.size + 1, dtype=np.int64)
    np.add.at(indptr, src + 1, 1)
    edges = _Edges(
        indptr=np.cumsum(indptr),
        dst=np.concatenate(dst_all)[order].astype(np.int64),
        offset=np.concatenate(off_all)[order].astype(np.int64),
        dist_m=np.concatenate(dist_all)[order],
        rate=np.concatenate(rate_all)[order],
    )
    _EDGES[key] = (weakref.ref(ls), edges)
    return edges


def arrival_times(
    ls: Landscape,
    ignition: int,
    phys: Physics,
    wind_from_deg: float,
    wind_ms: float,
    fuel_mult: float,
) -> NDArray[np.float64]:
    """Minutes for the fire to reach each cell (flat, row-major); inf where it never does
    within `phys.horizon_limit_min`."""
    e = _edges(ls, phys)
    speed = e.rate * fuel_mult * wind_factors(wind_from_deg, wind_ms, phys)[e.offset]
    graph = csr_matrix((e.dist_m / speed, e.dst, e.indptr), shape=(ls.size, ls.size))
    t = dijkstra(graph, directed=True, indices=ignition, limit=phys.horizon_limit_min)
    return np.asarray(t, dtype=np.float64)
