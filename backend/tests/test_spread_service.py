from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point, mapping
from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics
from wamidh_spread.run import TO_UTM, NodeRef, SpreadRun, Wind

from wamidh_backend.core import Incident, IncidentEvent, NodeInfo
from wamidh_backend.spread_service import SpreadService
from wamidh_backend.weather import WeatherService

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
TO_LONLAT = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
CFG: dict[str, Any] = {
    "ensemble": {
        "members": 60,
        "seed": 1,
        "wind_dir_sigma_deg": 25,
        "wind_dir_outliers": 0.1,
        "wind_speed_sigma_log": 0.35,
        "fuel_sigma_log": 0.3,
        "ignition_radius_m": 1200,
        "ignition_distance_sigma_m": 400,
        "ignition_upwind_sigma_deg": 45,
        "lag_min": [0, 4],
        "resample_below_ess": 0.3,
        "move_rounds": 3,
        "jitter": {
            "wind_dir_deg": 8,
            "wind_speed_rel": 0.1,
            "fuel_rel": 0.1,
            "ignition_m": 100,
            "lag_min": 1,
        },
    },
    "observations": {"detect_radius_m": 300, "sigma_min": 6, "sigma_rel": 0.2},
    "forecast": {"horizons_min": [15, 30, 60, 120], "bands": [0.2, 0.5, 0.8], "simplify_m": 40},
}
X, Y = 470_000.0, 4_075_000.0  # sensor 1, in UTM


def lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = TO_LONLAT.transform(x, y)
    return float(lon), float(lat)


NODES = [NodeInfo(i, b"k", *lonlat(X + 1000 * (i - 1), Y), None, None, None) for i in (1, 2, 3, 4)]


class FlatEngine:
    """The real filter on a flat 8 km shrubland window (no rasters needed)."""

    def __init__(self) -> None:
        self.started: list[Wind] = []

    def start(
        self, first: NodeRef, t0: datetime, wind: Wind, nodes: list[NodeRef], time_scale: float
    ) -> SpreadRun:
        self.started.append(wind)
        x, y = TO_UTM.transform(first.lon, first.lat)
        ls = Landscape.from_arrays(np.full((80, 80), 3.0), 100.0, x0=x - 4000, y0=y + 4000)
        return SpreadRun(
            ls, Physics(0.4, 8, 0.069, 0.035, 600), CFG, first, t0, wind, nodes, time_scale
        )


class FixedWind:
    def wind(self, lat: float, lon: float) -> tuple[float, float]:
        return 270.0, 6.0


def incident(
    status: str = "STATION_NOTIFIED", events: list[IncidentEvent] | None = None
) -> Incident:
    first = NODES[0]
    return Incident(
        id=7,
        status=status,
        first_node_id=1,
        estimated_origin={"lon": first.lon, "lat": first.lat},
        created_at=T0,
        access_point=None,
        events=events or [IncidentEvent(T0, "node_fire", {"node_id": 1})],
        node_ids={1},
    )


def zones() -> dict[str, Any]:
    east = Point(X + 400, Y).buffer(150)  # just downwind of sensor 1
    far = Point(X - 3500, Y + 3500).buffer(150)
    feats = [
        {
            "type": "Feature",
            "geometry": mapping(geom),
            "properties": {
                "id": zid,
                "name": name,
                "near": name,
                "population": 300,
                "risk_level": "high",
            },
        }  # fmt: skip
        for zid, name, geom in [(1, "east", east), (2, "far", far)]
    ]
    for f in feats:  # to WGS84
        from shapely.geometry import shape
        from shapely.ops import transform

        f["geometry"] = mapping(
            transform(lambda x, y, z=None: TO_LONLAT.transform(x, y), shape(f["geometry"]))
        )
    return {"type": "FeatureCollection", "features": feats}


def service(engine: FlatEngine | None = None, scale: float = 1.0) -> SpreadService:
    return SpreadService(
        engine or FlatEngine(),
        WeatherService(FixedWind(), cache_s=600, default={"from_deg": 0, "speed_ms": 0}),
        NODES,
        time_scale=scale,
        zones=zones,
    )


def test_forecast_uses_the_live_wind_and_names_the_threatened_zones() -> None:
    engine = FlatEngine()
    svc = service(engine)

    fc = svc.forecast(
        incident(), {1: "FIRE", 2: "NORMAL", 3: "NORMAL", 4: "NORMAL"}, T0 + timedelta(minutes=1)
    )

    assert fc is not None
    assert engine.started == [Wind(270.0, 6.0, "openweathermap")]
    assert fc["wind_reading"]["source"] == "openweathermap"
    assert fc["incident_id"] == 7 and fc["advisory"] is True
    assert 45 < fc["head"]["bearing_deg"] < 135  # running east with a west wind
    threatened = {z["id"]: z for z in fc["threatened_zones"]}
    assert 1 in threatened and 2 not in threatened
    assert threatened[1]["horizon_min"] in (0, 15, 30, 60, 120)
    assert threatened[1]["p"] in (0.2, 0.5, 0.8)


def test_audit_log_detections_feed_the_model_once() -> None:
    svc = service()
    events = [
        IncidentEvent(T0, "node_fire", {"node_id": 1}),
        IncidentEvent(T0 + timedelta(minutes=95), "fire_spread", {"node_id": 2}),
        IncidentEvent(T0 + timedelta(minutes=97), "node_lost", {"node_id": 1}),
    ]
    states = {1: "LOST_PROBABLY_BURNED", 2: "FIRE", 3: "NORMAL", 4: "NORMAL"}

    fc = svc.forecast(incident(events=events), states, T0 + timedelta(minutes=98))
    again = svc.forecast(incident(events=events), states, T0 + timedelta(minutes=99))

    assert fc is not None and again is not None
    assert [(o["node_id"], o["event"]) for o in fc["observed"]] == [
        (1, "FIRE"),
        (2, "FIRE"),
        (1, "LOST"),
    ]
    assert len(again["observed"]) == 3


def test_a_closed_incident_keeps_the_forecast_of_its_last_moment() -> None:
    svc = service()
    events = [
        IncidentEvent(T0, "node_fire", {"node_id": 1}),
        IncidentEvent(T0 + timedelta(minutes=30), "status", {"status": "CLOSED"}),
    ]

    fc = svc.forecast(incident("CLOSED", events), {1: "NORMAL"}, T0 + timedelta(days=1))

    assert fc is not None and fc["fire_minutes"] == 30.0


def test_demo_time_scale_is_reported() -> None:
    fc = service(scale=60).forecast(incident(), {1: "FIRE"}, T0 + timedelta(seconds=30))

    assert fc is not None and fc["time_scale"] == 60 and fc["fire_minutes"] == 30.0
