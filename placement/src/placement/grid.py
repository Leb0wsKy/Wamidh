"""Regular analysis grid in a metric CRS (EPSG:32632) and raster aggregation onto it."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from rasterio.transform import Affine

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass(frozen=True)
class Grid:
    """North-up grid. (x0, y0) is the top-left corner; rows go south, cols go east."""

    x0: float
    y0: float
    cell: float
    nrows: int
    ncols: int

    @classmethod
    def covering(cls, xmin: float, ymin: float, xmax: float, ymax: float, cell: float) -> Grid:
        """Smallest grid with corners on multiples of `cell` that contains the box."""
        x0 = math.floor(xmin / cell) * cell
        y0 = math.ceil(ymax / cell) * cell
        ncols = math.ceil((xmax - x0) / cell)
        nrows = math.ceil((y0 - ymin) / cell)
        return cls(x0=x0, y0=y0, cell=cell, nrows=nrows, ncols=ncols)

    @property
    def transform(self) -> Affine:
        return Affine(self.cell, 0, self.x0, 0, -self.cell, self.y0)

    def index(self, x: FloatArray, y: FloatArray) -> tuple[IntArray, IntArray]:
        """(row, col) of the cell containing each point; -1 for points outside the grid."""
        cols = np.floor((np.asarray(x) - self.x0) / self.cell).astype(np.int64)
        rows = np.floor((self.y0 - np.asarray(y)) / self.cell).astype(np.int64)
        outside = (rows < 0) | (rows >= self.nrows) | (cols < 0) | (cols >= self.ncols)
        rows[outside] = -1
        cols[outside] = -1
        return rows, cols

    def to_raster(self, rows: IntArray, cols: IntArray, values: FloatArray) -> FloatArray:
        """Full-grid array with `values` at (rows, cols) and NaN everywhere else."""
        out = np.full((self.nrows, self.ncols), np.nan)
        out[rows, cols] = values
        return out

    def window(
        self, xmin: float, ymin: float, xmax: float, ymax: float
    ) -> tuple[tuple[int, int, int, int], Grid]:
        """(row0, row1, col0, col1) slice bounds covering the box, and that sub-grid."""
        c0 = max(0, math.floor((xmin - self.x0) / self.cell))
        c1 = min(self.ncols, math.ceil((xmax - self.x0) / self.cell))
        r0 = max(0, math.floor((self.y0 - ymax) / self.cell))
        r1 = min(self.nrows, math.ceil((self.y0 - ymin) / self.cell))
        sub = Grid(
            x0=self.x0 + c0 * self.cell,
            y0=self.y0 - r0 * self.cell,
            cell=self.cell,
            nrows=r1 - r0,
            ncols=c1 - c0,
        )
        return (r0, r1, c0, c1), sub

    def centres(self, rows: IntArray, cols: IntArray) -> tuple[FloatArray, FloatArray]:
        x = self.x0 + (np.asarray(cols) + 0.5) * self.cell
        y = self.y0 - (np.asarray(rows) + 0.5) * self.cell
        return x.astype(np.float64), y.astype(np.float64)


def pixel_centres(shape: tuple[int, int], transform: Affine) -> tuple[FloatArray, FloatArray]:
    """x, y of every pixel centre of a north-up raster, as 2-D arrays."""
    rows, cols = np.indices(shape)
    x = transform.c + (cols + 0.5) * transform.a
    y = transform.f + (rows + 0.5) * transform.e
    return x.astype(np.float64), y.astype(np.float64)


def aggregate_mean(raster: FloatArray, transform: Affine, grid: Grid) -> FloatArray:
    """Mean of the raster pixels whose centres fall in each grid cell (NaN ignored).

    Cells with no valid pixel are NaN. Works for any source resolution, including
    ones that do not divide the cell size (90 m pixels into 375 m cells).
    """
    x, y = pixel_centres(raster.shape, transform)
    rows, cols = grid.index(x.ravel(), y.ravel())
    vals = np.asarray(raster, dtype=np.float64).ravel()
    ok = (rows >= 0) & ~np.isnan(vals)
    flat = rows[ok] * grid.ncols + cols[ok]
    size = grid.nrows * grid.ncols
    sums = np.bincount(flat, weights=vals[ok], minlength=size)
    counts = np.bincount(flat, minlength=size)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = sums / counts
    return out.reshape(grid.nrows, grid.ncols)
