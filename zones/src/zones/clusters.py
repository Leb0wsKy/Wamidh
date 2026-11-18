"""Settlements: DBSCAN on OSM building footprints and settled WorldPop cells (EPSG:32632).

OSM maps only part of the houses in Kroumirie; WorldPop constrained cells (people only where
buildings were detected on imagery) fill the gaps, so a village OSM has not mapped is a zone too.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
from shapely.ops import unary_union
from sklearn.cluster import DBSCAN


def cluster_buildings(
    footprints: gpd.GeoDataFrame,
    eps_m: float,
    min_buildings: int,
    buffer_m: float,
    simplify_m: float,
) -> gpd.GeoDataFrame:
    """One zone per group of at least `min_buildings` elements closer than `eps_m` to each other.

    Elements are OSM footprints and settled WorldPop cell centres; an optional `kind` column
    ("building" or "pixel") makes `building_count` count only the OSM footprints.

    The outline is the union of `buffer_m` buffers around the group's footprints, simplified to
    `simplify_m`. Isolated houses (DBSCAN noise) belong to no zone. Input and output: EPSG:32632.
    """
    if footprints.empty:
        return gpd.GeoDataFrame({"building_count": []}, geometry=[], crs=footprints.crs)
    centroids = footprints.geometry.centroid
    xy = np.column_stack([centroids.x, centroids.y])
    labels = DBSCAN(eps=eps_m, min_samples=min_buildings).fit_predict(xy)
    rows = []
    for label in sorted(set(labels) - {-1}):
        members = footprints.geometry[labels == label]
        outline = unary_union(members.buffer(buffer_m)).simplify(simplify_m)
        if "kind" in footprints.columns:
            count = int((footprints["kind"][labels == label] == "building").sum())
        else:
            count = int(len(members))
        rows.append({"building_count": count, "geometry": outline})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=footprints.crs)
