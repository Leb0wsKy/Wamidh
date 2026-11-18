"""Terrain line-of-sight between gateways and nodes on a DEM.

Radio feasibility check for LoRa links: a link is kept if the straight line between the
two antennas clears the terrain, with the Earth bulge corrected by the effective Earth
radius factor k (4/3 for standard atmospheric refraction). Fresnel-zone clearance is not
modelled; this is stated as a limitation in the report.

Grid positions are (row, col) indices into `dem`; `cell_m` is the square cell size.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage, sparse

EARTH_RADIUS_M = 6_371_000.0


def line_of_sight(
    dem: NDArray[np.float64],
    cell_m: float,
    a: tuple[int, int],
    b: tuple[int, int],
    h_a: float,
    h_b: float,
    earth_k: float,
) -> bool:
    """True if antenna at `a` (h_a above ground) sees antenna at `b` (h_b above ground)."""
    (r0, c0), (r1, c1) = a, b
    n = int(max(abs(r1 - r0), abs(c1 - c0)))
    if n <= 1:
        return True

    t = np.linspace(0.0, 1.0, n + 1)[1:-1]  # interior samples, one per cell step
    rows = np.rint(r0 + t * (r1 - r0)).astype(int)
    cols = np.rint(c0 + t * (c1 - c0)).astype(int)

    total_m = np.hypot(r1 - r0, c1 - c0) * cell_m
    d1 = t * total_m
    bulge = d1 * (total_m - d1) / (2.0 * earth_k * EARTH_RADIUS_M)

    z_a = dem[r0, c0] + h_a
    z_b = dem[r1, c1] + h_b
    sightline = z_a + t * (z_b - z_a)
    return bool(np.all(dem[rows, cols] + bulge < sightline))


def visibility_matrix(
    dem: NDArray[np.float64],
    cell_m: float,
    gateways_rc: NDArray[np.int_],
    nodes_rc: NDArray[np.int_],
    gateway_h: float,
    node_h: float,
    max_range_m: float,
    earth_k: float,
) -> sparse.csr_matrix:
    """Boolean (n_gateways x n_nodes) matrix of usable radio links."""
    rows: list[int] = []
    cols: list[int] = []
    for g, (gr, gc) in enumerate(gateways_rc):
        dist = np.hypot(nodes_rc[:, 0] - gr, nodes_rc[:, 1] - gc) * cell_m
        for j in np.flatnonzero(dist <= max_range_m):
            nr, nc = nodes_rc[j]
            if line_of_sight(dem, cell_m, (gr, gc), (nr, nc), gateway_h, node_h, earth_k):
                rows.append(g)
                cols.append(int(j))
    data = np.ones(len(rows), dtype=bool)
    return sparse.csr_matrix((data, (rows, cols)), shape=(len(gateways_rc), len(nodes_rc)))


def local_peaks(
    dem: NDArray[np.float64], window_px: int, min_percentile: float
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """(rows, cols) of hilltops: cells that are the highest within a `window_px` square and
    strictly above the `min_percentile` of elevations. Gateway mast candidates."""
    filled = np.where(np.isnan(dem), -np.inf, dem)
    threshold = np.nanpercentile(dem, min_percentile)
    is_peak = (filled == ndimage.maximum_filter(filled, size=window_px)) & (filled > threshold)
    rows, cols = np.nonzero(is_peak)
    return rows.astype(np.int64), cols.astype(np.int64)
