"""Population per zone from the WorldPop grid (people per pixel, a modelled estimate)."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from shapely.geometry import Point, box


def zone_population(zones: gpd.GeoDataFrame, raster: Path) -> list[int]:
    """Sum of the pixels whose centre falls inside each zone, rounded to the nearest 10."""
    out: list[int] = []
    with rasterio.open(raster) as src:
        for geom in zones.to_crs(src.crs).geometry:
            try:
                data, _ = mask(src, [geom], crop=True, filled=False)
            except ValueError:  # the zone lies outside the raster
                out.append(0)
                continue
            band = data[0]
            valid = band.compressed() if np.ma.isMaskedArray(band) else band.ravel()
            if src.nodata is not None:
                valid = valid[valid != src.nodata]
            valid = valid[np.isfinite(valid) & (valid > 0)]
            out.append(int(round(float(valid.sum()), -1)))
    return out


def settled_cells(raster: Path, bbox: tuple[float, ...], min_people: float) -> gpd.GeoDataFrame:
    """Centres of the WorldPop cells inside `bbox` holding at least `min_people`, as
    "pixel" elements in EPSG:32632 (a constrained grid has people only where buildings are)."""
    with rasterio.open(raster) as src:
        # `bbox` is lon/lat; the raster may use another CRS (the test grids are in metres).
        area = gpd.GeoSeries([box(*bbox)], crs="EPSG:4326").to_crs(src.crs).iloc[0]
        try:
            data, transform = mask(src, [area], crop=True, filled=False)
        except ValueError:  # the raster does not cover the area
            return gpd.GeoDataFrame({"kind": []}, geometry=[], crs="EPSG:32632")
        band = data[0]
        values = np.ma.filled(band.astype("float64"), 0.0)
        if src.nodata is not None:
            values[values == src.nodata] = 0.0
        rows, cols = np.nonzero(np.isfinite(values) & (values >= min_people))
        xs, ys = rasterio.transform.xy(transform, rows, cols)
        crs = src.crs
    points = [Point(x, y) for x, y in zip(xs, ys, strict=True)]
    cells = gpd.GeoDataFrame({"kind": ["pixel"] * len(points)}, geometry=points, crs=crs)
    return cells.to_crs("EPSG:32632")
