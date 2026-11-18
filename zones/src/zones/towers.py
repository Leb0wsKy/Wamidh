"""Cell towers from the OpenCelliD bulk download, and which towers serve each zone.

OpenCelliD is crowdsourced: positions are approximate and `range` is an estimate from the
measurements, not the coverage declared by the operator (ADR 0003). In a real alert the
operators pick the cells from the CAP polygon; this list is indicative.
"""

from __future__ import annotations

import csv
import gzip
from pathlib import Path
from typing import IO

import geopandas as gpd
from shapely.geometry import Point

# OpenCelliD bulk CSV columns, in order (the file may or may not start with this header).
COLUMNS = [
    "radio",
    "mcc",
    "net",
    "area",
    "cell",
    "unit",
    "lon",
    "lat",
    "range",
    "samples",
    "changeable",
    "created",
    "updated",
    "averageSignal",
]


class TowerFormatError(ValueError):
    """The file is not in the OpenCelliD bulk CSV format."""


def _open(path: Path) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open(encoding="utf-8", newline="")


def parse_towers(
    path: Path, bbox: tuple[float, float, float, float], pad_m: float
) -> gpd.GeoDataFrame:
    """Towers inside `bbox` (lon_min, lat_min, lon_max, lat_max) plus `pad_m`, in EPSG:4326."""
    pad_deg = pad_m / 111_000  # generous at 37 N; only a pre-filter
    x0, y0 = bbox[0] - pad_deg, bbox[1] - pad_deg
    x1, y1 = bbox[2] + pad_deg, bbox[3] + pad_deg
    rows = []
    with _open(path) as f:
        for k, rec in enumerate(csv.reader(f)):
            if k == 0 and rec and rec[0].strip().lower() == "radio":
                continue  # header row
            if len(rec) < 10:
                raise TowerFormatError(
                    f"{path.name} line {k + 1} has {len(rec)} fields; expected the OpenCelliD "
                    f"bulk format ({', '.join(COLUMNS[:10])}, ...)"
                )
            r = dict(zip(COLUMNS, rec, strict=False))
            try:
                lon, lat = float(r["lon"]), float(r["lat"])
                rng, samples = int(float(r["range"])), int(float(r["samples"]))
                net = int(r["net"])
            except ValueError as e:
                raise TowerFormatError(
                    f"{path.name} line {k + 1}: not OpenCelliD data ({e})"
                ) from e
            if x0 <= lon <= x1 and y0 <= lat <= y1:
                rows.append(
                    {
                        "id": f"{r['mcc']}-{r['net']}-{r['area']}-{r['cell']}",
                        "radio": r["radio"],
                        "net": net,
                        "range_m": rng,
                        "samples": samples,
                        "geometry": Point(lon, lat),
                    }
                )
    if not rows:
        return empty_towers()
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def empty_towers() -> gpd.GeoDataFrame:
    """No towers known (OpenCelliD not downloaded yet), with the usual columns."""
    empty = {"id": [], "radio": [], "net": [], "range_m": [], "samples": []}
    return gpd.GeoDataFrame(empty, geometry=[], crs="EPSG:4326")


def link_towers(
    zones: gpd.GeoDataFrame, towers: gpd.GeoDataFrame, min_range_m: float, max_range_m: float
) -> list[list[str]]:
    """Per zone, the sorted ids of the towers whose coverage circle (range clipped to
    [min, max]) intersects it; if none does, the nearest tower. Same projected CRS (metres)."""
    if towers.empty:
        return [[] for _ in range(len(zones))]
    radius = towers["range_m"].clip(lower=min_range_m, upper=max_range_m)
    circles = towers.geometry.buffer(radius, resolution=16)
    out: list[list[str]] = []
    for zone in zones.geometry:
        hit = sorted(towers.loc[circles.intersects(zone), "id"].astype(str))
        if not hit:
            nearest = int(towers.geometry.distance(zone).values.argmin())
            hit = [str(towers.iloc[nearest]["id"])]
        out.append(hit)
    return out
