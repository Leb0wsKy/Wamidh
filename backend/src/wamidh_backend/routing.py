"""Offline road routing on OpenStreetMap roads (CLAUDE.md s. 8: routing service).

The crew app must work without mobile data, so routes are computed here, on the Geofabrik road
extract already downloaded for the placement model: fastest path (Dijkstra) on a directed graph
that respects one-way roads, with turn-by-turn steps. Travel speeds per road class are
ASSUMPTIONS (OSM rarely tags maxspeed here); see backend/config/dev.yaml.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer
from scipy import sparse
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import LineString

LonLat = tuple[float, float]


@dataclass
class Step:
    kind: str  # depart | straight | slight_left | left | slight_right | right | uturn | arrive
    road: dict[str, Any]  # {"ref", "name", "fclass"} of the road taken
    distance_m: float  # length of this step
    location: list[float]  # [lon, lat] where the manoeuvre happens

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "road": self.road,
            "distance_m": round(self.distance_m, 1),
            "location": self.location,
        }


@dataclass
class Route:
    geometry: list[list[float]]  # [[lon, lat], ...]
    distance_m: float
    duration_s: float
    steps: list[Step] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "geometry": self.geometry,
            "distance_m": round(self.distance_m, 1),
            "duration_s": round(self.duration_s, 1),
            "steps": [s.to_json() for s in self.steps],
        }


def _text(v: Any) -> str | None:
    """Road label or None (shapefiles give NaN for missing values)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = str(v).strip()
    return v or None


def _turn(a: NDArray[np.float64], b: NDArray[np.float64]) -> float:
    """Signed turn angle in degrees from heading a to heading b (positive = left)."""
    cross = a[0] * b[1] - a[1] * b[0]
    dot = a[0] * b[0] + a[1] * b[1]
    return math.degrees(math.atan2(cross, dot))


def _kind(angle: float) -> str:
    a = abs(angle)
    if a < 20:
        return "straight"
    if a >= 150:
        return "uturn"
    side = "left" if angle > 0 else "right"
    return f"slight_{side}" if a < 60 else side


class RoadGraph:
    def __init__(
        self,
        lonlat: NDArray[np.float64],
        xy: NDArray[np.float64],
        edges: dict[tuple[int, int], tuple[float, float, dict[str, Any]]],
    ) -> None:
        self._lonlat = lonlat
        self._xy = xy
        self._edges = edges
        n = len(lonlat)
        rows, cols = zip(*edges, strict=True) if edges else ((), ())
        times = [edges[e][1] for e in edges]
        self._csr = sparse.csr_matrix((times, (rows, cols)), shape=(n, n))
        # Degree in the undirected sense: junctions are where a turn can be taken.
        und = self._csr + self._csr.T
        self._degree = np.diff(und.indptr)
        # Snap only to the largest connected part of the network, so a route always exists
        # between snapped points (small disconnected fragments are common in OSM extracts).
        _, labels = connected_components(self._csr, directed=True, connection="weak")
        main = np.bincount(labels).argmax() if n else 0
        self._snap_ids = np.flatnonzero(labels == main)
        self._tree = cKDTree(xy[self._snap_ids]) if n else None
        self._to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)

    @classmethod
    def from_lines(
        cls,
        lines: Sequence[LineString],
        attrs: Sequence[Mapping[str, Any]],
        speeds_kmh: Mapping[str, float],
    ) -> RoadGraph:
        to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
        index: dict[tuple[float, float], int] = {}
        lonlat: list[tuple[float, float]] = []

        def vertex(lon: float, lat: float) -> int:
            key = (round(lon, 7), round(lat, 7))
            if key not in index:
                index[key] = len(lonlat)
                lonlat.append((lon, lat))
            return index[key]

        raw: list[tuple[int, int, str, dict[str, Any]]] = []
        for line, a in zip(lines, attrs, strict=True):
            speed = speeds_kmh.get(a["fclass"])
            if not speed:
                continue  # road class not drivable (footpaths, steps, ...)
            road = {"ref": _text(a.get("ref")), "name": _text(a.get("name")), "fclass": a["fclass"]}
            coords = list(line.coords)
            ids = [vertex(x, y) for x, y in coords]
            for i, j in zip(ids, ids[1:], strict=False):
                if i != j:
                    raw.append((i, j, a.get("oneway") or "B", {**road, "_speed": speed}))

        ll = np.asarray(lonlat, dtype=np.float64).reshape(-1, 2)
        xs, ys = to_utm.transform(ll[:, 0], ll[:, 1]) if len(ll) else ([], [])
        xy = np.column_stack([xs, ys]).astype(np.float64) if len(ll) else np.zeros((0, 2))

        edges: dict[tuple[int, int], tuple[float, float, dict[str, Any]]] = {}
        for i, j, oneway, road in raw:
            length = float(np.hypot(*(xy[j] - xy[i])))
            time = length / (road["_speed"] / 3.6)
            info = {k: v for k, v in road.items() if k != "_speed"}
            directions = {"F": [(i, j)], "T": [(j, i)]}.get(oneway, [(i, j), (j, i)])
            for e in directions:
                if e not in edges or edges[e][1] > time:
                    edges[e] = (length, time, info)
        return cls(ll, xy, edges)

    @classmethod
    def from_shapefile(
        cls, path: Path, bbox: tuple[float, float, float, float], speeds_kmh: Mapping[str, float]
    ) -> RoadGraph:
        import geopandas as gpd

        roads = gpd.read_file(path, bbox=bbox, columns=["fclass", "name", "ref", "oneway"])
        roads = roads[roads.fclass.isin(list(speeds_kmh))].explode(index_parts=False)
        attrs = [
            {"fclass": r.fclass, "name": r["name"], "ref": r["ref"], "oneway": r.oneway}
            for _, r in roads.iterrows()
        ]
        return cls.from_lines(list(roads.geometry), attrs, speeds_kmh)

    @property
    def size(self) -> tuple[int, int]:
        return len(self._lonlat), len(self._edges)

    def _snap(self, point: LonLat) -> int:
        x, y = self._to_utm.transform(point[0], point[1])
        assert self._tree is not None
        _, k = self._tree.query([x, y])
        return int(self._snap_ids[int(k)])

    def route(self, origin: LonLat, dest: LonLat) -> Route | None:
        if self._tree is None:
            return None
        o, d = self._snap(origin), self._snap(dest)
        dist, pred = dijkstra(self._csr, indices=o, return_predecessors=True)
        if not np.isfinite(dist[d]):
            return None
        path = [d]
        while path[-1] != o:
            path.append(int(pred[path[-1]]))
        path.reverse()
        return self._describe(path)

    def _describe(self, path: list[int]) -> Route:
        geometry = [[float(self._lonlat[v][0]), float(self._lonlat[v][1])] for v in path]
        edges = [self._edges[(a, b)] for a, b in zip(path, path[1:], strict=False)]
        route = Route(
            geometry=geometry,
            distance_m=sum(e[0] for e in edges),
            duration_s=sum(e[1] for e in edges),
        )
        if not edges:
            route.steps = [Step("arrive", {}, 0.0, geometry[0])]
            return route

        def identity(road: dict[str, Any]) -> tuple[Any, ...]:
            return (road["ref"] or road["name"] or road["fclass"],)

        steps = [Step("depart", edges[0][2], 0.0, geometry[0])]
        for k, (length, _, road) in enumerate(edges):
            if k > 0:
                v = path[k]
                angle = _turn(
                    self._xy[v] - self._xy[path[k - 1]], self._xy[path[k + 1]] - self._xy[v]
                )
                changed = identity(road) != identity(edges[k - 1][2])
                if changed or (self._degree[v] >= 3 and abs(angle) >= 35):
                    steps.append(Step(_kind(angle), road, 0.0, geometry[k]))
            steps[-1].distance_m += length
        steps.append(Step("arrive", edges[-1][2], 0.0, geometry[-1]))
        route.steps = steps
        return route
