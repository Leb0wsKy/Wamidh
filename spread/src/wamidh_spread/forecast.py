"""What the spread engine tells the station: probability contours per horizon, ignition, head
direction and speed, the sensors likely to be reached next, and the model's confidence."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer
from rasterio.features import shapes
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

if TYPE_CHECKING:
    from wamidh_spread.landscape import Landscape
    from wamidh_spread.run import Wind

TO_LONLAT = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)


@dataclass(frozen=True)
class NodeOutlook:
    node_id: int
    p_within_60: float
    p_within_120: float
    eta_min: float  # median expected detection, fire minutes from now (inf: not expected)


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = TO_LONLAT.transform(x, y)
    return round(float(lon), 6), round(float(lat), 6)


@dataclass
class Forecast:
    landscape: Landscape
    computed_at: datetime
    fire_minutes: float  # since the first detection
    time_scale: float
    probabilities: dict[int, NDArray[np.float64]]  # horizon (min from now) -> P(burned), flat
    bands: list[float]
    simplify_m: float
    ignition_xy: tuple[float, float]
    ignition_uncertainty_m: float
    ignition_at: datetime
    heading_deg: float
    speed_m_min: float
    wind_from_deg: float  # the wind the evidence points to
    wind_ms: float
    wind_observed: Wind
    members: int
    ess_ratio: float
    observed: list[tuple[int, str, datetime]]
    next_nodes: list[NodeOutlook] = field(default_factory=list)

    def probability(self, horizon_min: int) -> NDArray[np.float64]:
        return self.probabilities[horizon_min].reshape(self.landscape.rows, self.landscape.cols)

    def area_ha(self, horizon_min: int, p: float = 0.5) -> float:
        cells = int((self.probabilities[horizon_min] >= p).sum())
        return cells * self.landscape.cell_m**2 / 10_000

    def contours(self, horizon_min: int) -> dict[str, Any]:
        """Areas burned by then with probability >= each band, as WGS84 polygons."""
        grid = self.probability(horizon_min)
        features = []
        for band in self.bands:
            mask = (grid >= band).astype(np.uint8)
            if not mask.any():
                continue
            polys = [
                shape(geom)
                for geom, value in shapes(
                    mask, mask=mask.astype(bool), transform=self.landscape.transform
                )
                if value == 1
            ]
            merged = unary_union(polys).simplify(self.simplify_m, preserve_topology=True)
            features.append(
                {
                    "type": "Feature",
                    "properties": {"p": band, "horizon_min": horizon_min},
                    "geometry": mapping(
                        transform(lambda x, y, z=None: TO_LONLAT.transform(x, y), merged)
                    ),
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def to_json(self) -> dict[str, Any]:
        ix, iy = self.ignition_xy
        lon, lat = _lonlat(ix, iy)
        finite = math.isfinite(self.heading_deg)
        return {
            "computed_at": _iso(self.computed_at),
            "fire_minutes": round(self.fire_minutes, 1),
            "time_scale": self.time_scale,
            "ignition": {
                "lon": lon,
                "lat": lat,
                "uncertainty_m": round(self.ignition_uncertainty_m),
                "at": _iso(self.ignition_at),
            },
            "head": {
                "bearing_deg": round(self.heading_deg, 1) if finite else None,
                "speed_m_min": round(self.speed_m_min, 1),
            },
            "wind": {
                "estimated_from_deg": round(self.wind_from_deg, 1),
                "estimated_speed_ms": round(self.wind_ms, 1),
                "observed_from_deg": round(self.wind_observed.from_deg, 1),
                "observed_speed_ms": round(self.wind_observed.speed_ms, 1),
                "source": self.wind_observed.source,
            },
            "confidence": {"members": self.members, "ess_ratio": round(self.ess_ratio, 3)},
            "area_ha": {str(h): round(self.area_ha(h), 1) for h in self.probabilities},
            "horizons": {str(h): self.contours(h) for h in self.probabilities},
            "observed": [
                {"node_id": nid, "event": kind, "at": _iso(t)} for nid, kind, t in self.observed
            ],
            "next_nodes": [
                {
                    "node_id": o.node_id,
                    "p_within_60": round(o.p_within_60, 2),
                    "p_within_120": round(o.p_within_120, 2),
                    "eta_min": round(o.eta_min, 1) if math.isfinite(o.eta_min) else None,
                }
                for o in self.next_nodes
            ],
        }
