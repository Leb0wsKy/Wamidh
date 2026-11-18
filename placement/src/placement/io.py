"""Shared I/O: rasters, step entry points, names."""

from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from numpy.typing import NDArray
from rasterio.transform import Affine

from placement.config import load_config

# ESA WorldCover v200 class codes -> band suffix used in the GEE landcover export.
WORLDCOVER_CLASSES = {
    10: "tree",
    20: "shrub",
    30: "grass",
    40: "crop",
    50: "built",
    60: "bare",
    80: "water",
    90: "wetland",
}


@dataclass
class Raster:
    bands: dict[str, NDArray[np.float64]]
    transform: Affine
    crs: str

    @property
    def pixel_m(self) -> float:
        return float(self.transform.a)


def read_raster(path: Path) -> Raster:
    """All bands as float64 keyed by band description; nodata values become NaN."""
    with rasterio.open(path) as src:
        bands = {}
        for i in range(1, src.count + 1):
            arr = src.read(i).astype(np.float64)
            if src.nodata is not None:
                arr[arr == src.nodata] = np.nan
            bands[src.descriptions[i - 1] or f"band{i}"] = arr
        return Raster(bands=bands, transform=src.transform, crs=str(src.crs))


def normalise_name(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def step_main(run: Callable[[dict[str, Any]], None], description: str) -> None:
    """Command-line entry point shared by the pipeline steps."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    run(load_config(args.config))


def write_geotiff(
    path: Path,
    bands: dict[str, NDArray[np.float64]],
    transform: Affine,
    crs: str,
    tags: dict[str, str] | None = None,
) -> None:
    """Float32 GeoTIFF, one band per entry (band description = key), NaN as nodata."""
    arrays = list(bands.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=arrays[0].shape[0],
        width=arrays[0].shape[1],
        count=len(arrays),
        dtype="float32",
        crs=crs,
        transform=transform,
        nodata=np.nan,
        compress="deflate",
    ) as dst:
        for i, (name, arr) in enumerate(bands.items(), start=1):
            dst.write(arr.astype(np.float32), i)
            dst.set_band_description(i, name)
        if tags:
            dst.update_tags(**tags)
