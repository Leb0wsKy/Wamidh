"""Fire risk of a zone: the most susceptible forest around it, from the placement model.

Band 2 of the susceptibility GeoTIFF is the percentile among wildland cells of northern Tunisia.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask

PERCENTILE_BAND = 2


def zone_risk(
    zones: gpd.GeoDataFrame, raster: Path, ring_m: float, high: float, medium: float
) -> list[tuple[str, float | None]]:
    """(level, max percentile) per zone over wildland cells within `ring_m` of it.

    Level: high at `high` or above, medium at `medium` or above, low otherwise, and none when
    no forest lies within the ring.
    """
    out: list[tuple[str, float | None]] = []
    with rasterio.open(raster) as src:
        rings = zones.to_crs("EPSG:32632").geometry.buffer(ring_m).to_crs(src.crs)
        for ring in rings:
            try:
                data, _ = mask(src, [ring], crop=True, indexes=PERCENTILE_BAND, filled=False)
            except ValueError:  # outside the raster
                out.append(("none", None))
                continue
            vals = data.compressed() if np.ma.isMaskedArray(data) else data.ravel()
            vals = vals[np.isfinite(vals)]
            if vals.size == 0:
                out.append(("none", None))
                continue
            top = round(float(vals.max()), 1)
            level = "high" if top >= high else "medium" if top >= medium else "low"
            out.append((level, top))
    return out
