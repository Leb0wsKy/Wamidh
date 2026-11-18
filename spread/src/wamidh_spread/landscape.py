"""The ground the fire runs over: a regular grid (EPSG:32632) of base rate of spread, slope and
aspect, cut from the pilot-zone rasters around a point."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject

UTM = "EPSG:32632"
Float = NDArray[np.float64]


@dataclass(frozen=True)
class Landscape:
    """Row 0 is the northern edge. Cell (i, j) centre: x0 + (j + 0.5) cell, y0 - (i + 0.5) cell."""

    rows: int
    cols: int
    cell_m: float
    x0: float  # west edge, UTM metres
    y0: float  # north edge
    ros: Float  # base rate of spread, m/min (0 = does not burn)
    slope_deg: Float
    upslope_az_deg: Float  # direction of steepest ascent, degrees from north, clockwise

    # --- construction ----------------------------------------------------------------------

    @staticmethod
    def from_arrays(
        ros: Float,
        cell_m: float,
        elevation: Float | None = None,
        x0: float = 0.0,
        y0: float = 0.0,
    ) -> Landscape:
        rows, cols = ros.shape
        elev = np.zeros_like(ros, dtype=float) if elevation is None else elevation.astype(float)
        # np.gradient: d/d(row) points south, d/d(col) points east.
        d_row, d_col = np.gradient(elev, cell_m)
        east, north = d_col, -d_row
        slope = np.degrees(np.arctan(np.hypot(east, north)))
        upslope = (np.degrees(np.arctan2(east, north)) + 360.0) % 360.0
        return Landscape(
            rows, cols, cell_m, x0, y0, ros.astype(float), slope, upslope.astype(float)
        )

    @staticmethod
    def uniform(
        rows: int, cols: int, cell_m: float, ros: float, elevation: Float | None = None
    ) -> Landscape:
        return Landscape.from_arrays(np.full((rows, cols), ros), cell_m, elevation)

    @staticmethod
    def from_rasters(
        terrain: Path,
        landcover: Path,
        ndvi: Path,
        fuels: dict[str, Any],
        centre_xy: tuple[float, float],
        window_m: float,
        cell_m: float,
    ) -> Landscape:
        """Cut a square window centred on `centre_xy` (UTM) and resample it to `cell_m`.
        Slope and aspect are recomputed from the resampled elevation (averaging aspect would be
        wrong: it is an angle). Outside the rasters the ground does not burn."""
        n = int(round(window_m / cell_m))
        x0 = centre_xy[0] - n * cell_m / 2
        y0 = centre_xy[1] + n * cell_m / 2
        transform = Affine(cell_m, 0.0, x0, 0.0, -cell_m, y0)

        def read(path: Path, band: int, how: Resampling, nodata: float) -> Float:
            out = np.full((n, n), nodata, dtype=np.float64)
            with rasterio.open(path) as src:
                reproject(
                    source=rasterio.band(src, band),
                    destination=out,
                    dst_transform=transform,
                    dst_crs=UTM,
                    resampling=how,
                    dst_nodata=nodata,
                )
            return out

        elev = read(terrain, 1, Resampling.average, np.nan)
        cover = read(landcover, 1, Resampling.mode, 0)
        green = read(ndvi, 1, Resampling.average, np.nan)

        ros = fuel_ros(cover, green, fuels)
        outside = np.isnan(elev)
        ros[outside] = 0.0
        elev = np.where(outside, np.nanmean(elev) if np.isfinite(elev).any() else 0.0, elev)
        return Landscape.from_arrays(ros, cell_m, elev, x0, y0)

    # --- indexing --------------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self.rows * self.cols

    @property
    def transform(self) -> Affine:
        return Affine(self.cell_m, 0.0, self.x0, 0.0, -self.cell_m, self.y0)

    def index(self, i: int, j: int) -> int:
        return i * self.cols + j

    def cell_of(self, x: float, y: float) -> int | None:
        """Flat index of the cell containing UTM point (x, y), or None outside the grid."""
        j = int((x - self.x0) // self.cell_m)
        i = int((self.y0 - y) // self.cell_m)
        if 0 <= i < self.rows and 0 <= j < self.cols:
            return self.index(i, j)
        return None

    def centre_of(self, idx: int) -> tuple[float, float]:
        i, j = divmod(idx, self.cols)
        return self.x0 + (j + 0.5) * self.cell_m, self.y0 - (i + 0.5) * self.cell_m

    def centres(self) -> tuple[Float, Float]:
        """UTM x and y of every cell centre, flat (row-major)."""
        jj, ii = np.meshgrid(np.arange(self.cols), np.arange(self.rows))
        xs = self.x0 + (jj.ravel() + 0.5) * self.cell_m
        ys = self.y0 - (ii.ravel() + 0.5) * self.cell_m
        return xs.astype(float), ys.astype(float)

    def cells_within(self, x: float, y: float, radius_m: float) -> NDArray[np.int64]:
        xs, ys = self.centres()
        near = np.flatnonzero(np.hypot(xs - x, ys - y) <= max(radius_m, self.cell_m / 2))
        if near.size == 0:
            own = self.cell_of(x, y)
            return np.array([] if own is None else [own], dtype=np.int64)
        return near.astype(np.int64)


def fuel_ros(cover: Float, ndvi: Float, fuels: dict[str, Any]) -> Float:
    """Base rate of spread per cell from the land-cover class, modulated by NDVI."""
    ros = np.zeros_like(cover, dtype=float)
    for code, spec in fuels["classes"].items():
        ros[cover == int(code)] = float(spec["ros_m_min"])
    m = fuels["ndvi"]
    green = np.where(np.isfinite(ndvi), ndvi, m["reference"])
    mult = np.clip(1 + m["slope"] * (m["reference"] - green), m["low"], m["high"])
    return np.asarray(ros * mult, dtype=np.float64)
