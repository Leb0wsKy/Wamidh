"""Raster and vector feature helpers. Coordinates are metric (EPSG:32632)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import shapely
from numpy.typing import NDArray
from rasterio.transform import Affine
from scipy import ndimage
from scipy.spatial import cKDTree
from shapely.geometry.base import BaseGeometry

FloatArray = NDArray[np.float64]


def distance_to_lines(x: FloatArray, y: FloatArray, lines: Sequence[BaseGeometry]) -> FloatArray:
    """Exact distance from each point to the nearest line (NaN if there are no lines)."""
    if len(lines) == 0:
        return np.full(len(x), np.nan)
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    points = shapely.points(x, y)
    _, dist = tree.query_nearest(points, return_distance=True, all_matches=False)
    return np.asarray(dist, dtype=np.float64)


def distance_to_points(x: FloatArray, y: FloatArray, pts: Sequence[BaseGeometry]) -> FloatArray:
    if len(pts) == 0:
        return np.full(len(x), np.nan)
    coords = shapely.get_coordinates(np.asarray(pts, dtype=object))
    dist, _ = cKDTree(coords).query(np.column_stack([x, y]))
    return np.asarray(dist, dtype=np.float64)


def distance_to_mask(mask: NDArray[np.bool_], pixel_m: float) -> FloatArray:
    """Euclidean distance (m) from every pixel to the nearest True pixel."""
    if not mask.any():
        return np.full(mask.shape, np.inf)
    return np.asarray(ndimage.distance_transform_edt(~mask, sampling=pixel_m), dtype=np.float64)


def _rowcol(transform: Affine, x: FloatArray, y: FloatArray) -> tuple[NDArray, NDArray]:
    cols = np.floor((np.asarray(x) - transform.c) / transform.a).astype(np.int64)
    rows = np.floor((np.asarray(y) - transform.f) / transform.e).astype(np.int64)
    return rows, cols


def sample_raster(
    raster: FloatArray, transform: Affine, x: FloatArray, y: FloatArray
) -> FloatArray:
    """Value of the pixel containing each point; NaN outside the raster."""
    rows, cols = _rowcol(transform, x, y)
    inside = (rows >= 0) & (rows < raster.shape[0]) & (cols >= 0) & (cols < raster.shape[1])
    out = np.full(len(rows), np.nan)
    out[inside] = raster[rows[inside], cols[inside]]
    return out


def fill_nan_nearest(raster: FloatArray) -> FloatArray:
    """Replace NaN pixels by the nearest valid pixel (e.g. coastal gaps in ERA5-Land)."""
    nan = np.isnan(raster)
    if not nan.any():
        return raster.copy()
    idx = ndimage.distance_transform_edt(nan, return_distances=False, return_indices=True)
    return np.asarray(raster[tuple(idx)], dtype=np.float64)


def window_mean(
    raster: FloatArray, transform: Affine, x: FloatArray, y: FloatArray, half_m: float
) -> FloatArray:
    """Mean of pixels whose centres lie in the square [x±half_m] x [y±half_m] (NaN ignored).

    Used to measure what is under a satellite footprint (375 m VIIRS, 1 km MODIS),
    e.g. the cropland fraction around a detection. Summed-area tables keep it O(n).
    """
    px, py = transform.a, -transform.e
    vals = np.nan_to_num(raster, nan=0.0)
    valid = (~np.isnan(raster)).astype(np.float64)
    s = np.pad(vals.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    c = np.pad(valid.cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    nrows, ncols = raster.shape
    c0 = np.clip(np.ceil((x - half_m - transform.c) / px - 0.5), 0, ncols).astype(int)
    c1 = np.clip(np.floor((x + half_m - transform.c) / px - 0.5) + 1, 0, ncols).astype(int)
    r0 = np.clip(np.ceil((transform.f - (y + half_m)) / py - 0.5), 0, nrows).astype(int)
    r1 = np.clip(np.floor((transform.f - (y - half_m)) / py - 0.5) + 1, 0, nrows).astype(int)

    def box(t: FloatArray) -> FloatArray:
        return t[r1, c1] - t[r0, c1] - t[r1, c0] + t[r0, c0]

    total, count = box(s), box(c)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def count_within(
    x: FloatArray, y: FloatArray, px: FloatArray, py: FloatArray, radius_m: float
) -> NDArray[np.int64]:
    """Number of points (px, py) within `radius_m` of each (x, y), boundary included."""
    if len(px) == 0:
        return np.zeros(len(x), dtype=np.int64)
    tree = cKDTree(np.column_stack([px, py]))
    counts = tree.query_ball_point(np.column_stack([x, y]), r=radius_m, return_length=True)
    return np.asarray(counts, dtype=np.int64)
