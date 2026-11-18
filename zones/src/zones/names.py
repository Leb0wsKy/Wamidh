"""Zone names from OpenStreetMap places (Arabic in the OSM data for Tunisia)."""

from __future__ import annotations

import geopandas as gpd


def name_zones(
    zones: gpd.GeoDataFrame, places: gpd.GeoDataFrame, radius_m: float
) -> list[dict[str, str | None]]:
    """Per zone: `name` is the nearest place within `radius_m`, else None (a douar), and `near`
    is the nearest place at any distance (for "douar near X"). Both inputs in the same CRS."""
    out: list[dict[str, str | None]] = []
    for zone in zones.geometry:
        if places.empty:
            out.append({"name": None, "near": None})
            continue
        dist = places.geometry.distance(zone)
        i = int(dist.values.argmin())
        nearest = str(places.iloc[i]["name"])
        out.append({"name": nearest if float(dist.iloc[i]) <= radius_m else None, "near": nearest})
    return out
