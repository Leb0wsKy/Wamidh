"""Export placement outputs for the backend and web app (web/public/placement/).

    python -m placement.export_web --config config/pilot_kroumirie.yaml

Writes:
  nodes.geojson      optimised sensor sites (id, rank, risk percentile, gateway)
  gateways.geojson   hilltop gateways
  risk.png           pilot susceptibility percentile, Wamidh ramp, reprojected to Web
                     Mercator so Leaflet's ImageOverlay places it correctly
  risk.json          {"url": "...", "bounds": [[south, west], [north, east]]}
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from numpy.typing import NDArray
from PIL import Image
from pyproj import Transformer
from rasterio.warp import Resampling, calculate_default_transform, reproject
from shapely.geometry.base import BaseGeometry

from placement.config import load_config
from placement.report import risk_cmap

WEB_MERCATOR = "EPSG:3857"


def colorize_percentile(pct: NDArray[np.float64], alpha: int) -> NDArray[np.uint8]:
    """RGBA image of a 0-100 percentile raster on the Wamidh ramp; NaN is transparent."""
    valid = ~np.isnan(pct)
    rgba = (risk_cmap()(np.nan_to_num(pct, nan=0.0) / 100.0) * 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, alpha, 0).astype(np.uint8)
    return rgba


def nearest_access(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    lines: Sequence[BaseGeometry],
    kinds: Sequence[str],
) -> tuple[NDArray[np.float64], NDArray[np.float64], list[str]]:
    """Closest point on the access network (and its OSM class) for each (x, y), metric CRS.

    This is where a crew leaves the vehicle: the demo's stand-in for the backend's
    precomputed access points."""
    tree = shapely.STRtree(np.asarray(lines, dtype=object))
    points = shapely.points(x, y)
    point_i, line_i = tree.query_nearest(points, all_matches=False)  # (2, n): input, tree
    hit = np.asarray(lines, dtype=object)[line_i]
    snapped = shapely.get_coordinates(shapely.shortest_line(points[point_i], hit))[1::2]
    return snapped[:, 0], snapped[:, 1], [kinds[i] for i in line_i]


def _risk_overlay(tif: Path, out_dir: Path) -> dict[str, Any]:
    with rasterio.open(tif) as src:
        pct = src.read(2).astype(np.float64)
        transform, width, height = calculate_default_transform(
            src.crs, WEB_MERCATOR, src.width, src.height, *src.bounds
        )
        merc = np.full((height, width), np.nan)
        reproject(
            pct,
            merc,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=WEB_MERCATOR,
            resampling=Resampling.nearest,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    Image.fromarray(colorize_percentile(merc, alpha=190), mode="RGBA").save(out_dir / "risk.png")
    left, top = transform.c, transform.f
    right, bottom = left + width * transform.a, top + height * transform.e
    to_ll = Transformer.from_crs(WEB_MERCATOR, "EPSG:4326", always_xy=True)
    west, south = to_ll.transform(left, bottom)
    east, north = to_ll.transform(right, top)
    return {"url": "/placement/risk.png", "bounds": [[south, west], [north, east]]}


def run(cfg: dict[str, Any], out_dir: Path) -> None:
    processed = cfg["paths"]["processed"]
    out_dir.mkdir(parents=True, exist_ok=True)

    nodes = gpd.read_file(processed / "nodes.geojson")
    nodes = nodes[
        ["node_id", "rank", "risk_percentile", "gateway_id", "dist_to_access_m", "geometry"]
    ]

    # Nearest road/track point per node: where the crew leaves the vehicle.
    metric = cfg["crs"]["metric"]
    w, s, e, n = cfg["pilot_zone"]["bbox"]
    pad = 0.02
    roads = gpd.read_file(
        cfg["paths"]["raw"] / "osm" / "gis_osm_roads_free_1.shp",
        bbox=(w - pad, s - pad, e + pad, n + pad),
        columns=["fclass"],
    ).to_crs(metric)
    fc = cfg["features"]
    roads = roads[roads.fclass.isin(fc["road_classes"] + fc["track_classes"])]
    nm = nodes.to_crs(metric)
    ax, ay, kinds = nearest_access(
        nm.geometry.x.to_numpy(),
        nm.geometry.y.to_numpy(),
        list(roads.geometry),
        list(roads.fclass),
    )
    to_ll = Transformer.from_crs(metric, "EPSG:4326", always_xy=True)
    lon, lat = to_ll.transform(ax, ay)
    nodes = nodes.assign(
        access_lon=np.round(lon, 6), access_lat=np.round(lat, 6), access_type=kinds
    )
    nodes.to_file(out_dir / "nodes.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)
    gws = gpd.read_file(processed / "gateways.geojson")
    gws = gws[["gateway_id", "elevation_m", "nodes_assigned", "geometry"]]
    gws.to_file(out_dir / "gateways.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)

    overlay = _risk_overlay(processed / f"susceptibility_{cfg['pilot_zone']['name']}.tif", out_dir)
    (out_dir / "risk.json").write_text(json.dumps(overlay, indent=2), encoding="utf-8")
    print(f"exported {len(nodes)} nodes, {len(gws)} gateways, risk overlay to {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export placement outputs for the web demo")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", help="output folder (default: <repo>/web/public/demo)")
    args = parser.parse_args()
    cfg = load_config(args.config)
    out = Path(args.out) if args.out else cfg["root"] / "web" / "public" / "placement"
    run(cfg, out)


if __name__ == "__main__":
    main()
