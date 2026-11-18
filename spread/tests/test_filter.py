"""The particle filter recovers a hidden fire from sensor alerts alone (ADR 0004)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest
from pyproj import Transformer

from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics, arrival_times
from wamidh_spread.run import NodeRef, SpreadRun, Wind

PHYS = Physics(0.4, 8.0, 0.069, 0.035, 600)
CFG: dict[str, Any] = {
    "ensemble": {
        "members": 150,
        "seed": 3,
        "wind_dir_sigma_deg": 30,
        "wind_dir_outliers": 0.1,
        "wind_speed_sigma_log": 0.35,
        "fuel_sigma_log": 0.3,
        "ignition_radius_m": 1200,
        "ignition_distance_sigma_m": 400,
        "ignition_upwind_sigma_deg": 45,
        "lag_min": [0, 4],
        "resample_below_ess": 0.3,
        "move_rounds": 6,
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
X0, Y0, CELL, N = 470_000.0, 4_080_000.0, 100.0, 100
TO_LONLAT = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


def landscape() -> Landscape:
    return Landscape.from_arrays(np.full((N, N), 3.0), CELL, x0=X0, y0=Y0)


def node(node_id: int, x: float, y: float) -> NodeRef:
    lon, lat = TO_LONLAT.transform(x, y)
    return NodeRef(node_id, lon, lat)


class Truth:
    """A hidden fire: ignition at the grid centre, wind from the west (it runs east)."""

    def __init__(self, ls: Landscape, wind_from: float = 270, wind_ms: float = 6) -> None:
        self.ls = ls
        self.ign = ls.index(N // 2 + 5, N // 2 + 3)  # 160 m west-south-west of sensor 505
        self.arrival = arrival_times(ls, self.ign, PHYS, wind_from, wind_ms, 1.0)
        # Sensors every 1 km.
        self.nodes = [
            node(100 * i + j, X0 + 500 + 1000 * j, Y0 - 500 - 1000 * i)
            for i in range(N // 10)
            for j in range(N // 10)
        ]

    def detection(self, n: NodeRef) -> float:
        x, y = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True).transform(
            n.lon, n.lat
        )
        cells = self.ls.cells_within(x, y, 300)
        return float(self.arrival[cells].min()) + 2.0  # 2 min detection lag

    def order(self) -> list[tuple[float, NodeRef]]:
        return sorted(
            (self.detection(n), n) for n in self.nodes if math.isfinite(self.detection(n))
        )


def heading_error(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def start(truth: Truth, wind: Wind) -> tuple[SpreadRun, list[tuple[float, NodeRef]]]:
    order = truth.order()
    t_first, first = order[0]
    run = SpreadRun(truth.ls, PHYS, CFG, first, T0, wind, truth.nodes, time_scale=1.0)
    # Times relative to the first detection, which happens at T0.
    return run, [(t - t_first, n) for t, n in order]


def test_after_one_detection_the_forecast_follows_the_measured_wind() -> None:
    truth = Truth(landscape())
    run, _ = start(truth, Wind(from_deg=270, speed_ms=6, source="test"))

    fc = run.forecast(T0 + timedelta(minutes=1), calm=set())

    assert heading_error(fc.heading_deg, 90) < 30
    assert 0.25 < fc.ess_ratio <= 1


def test_later_detections_correct_a_wrong_wind_and_locate_the_ignition() -> None:
    truth = Truth(landscape(), wind_from=270)
    # The measured wind is 50 degrees off: the fire really runs east, the forecast first says
    # north-east.
    run, order = start(truth, Wind(from_deg=220, speed_ms=6, source="test"))
    before = run.forecast(T0 + timedelta(minutes=1), calm=set())

    seen = order[:4]
    for t, n in seen[1:]:
        run.observe(n.node_id, "FIRE", T0 + timedelta(minutes=t))
    now = T0 + timedelta(minutes=seen[-1][0] + 1)
    calm = {n.node_id for n in truth.nodes} - {n.node_id for _, n in seen}
    after = run.forecast(now, calm=calm)

    assert heading_error(before.heading_deg, 90) > heading_error(after.heading_deg, 90)
    assert heading_error(after.heading_deg, 90) < 20
    assert heading_error(after.wind_from_deg, 270) < 25
    ix, iy = truth.ls.centre_of(truth.ign)
    assert math.hypot(after.ignition_xy[0] - ix, after.ignition_xy[1] - iy) < 500


def test_calm_sensors_rule_out_directions() -> None:
    truth = Truth(landscape(), wind_from=270)
    run, order = start(truth, Wind(from_deg=270, speed_ms=6, source="test"))
    t_first, first = order[0]
    # 40 minutes later, nobody else has detected anything: a slow fire, so the forecast must
    # slow down compared with one that has no news at all.
    later = T0 + timedelta(minutes=40)
    calm = {n.node_id for n in truth.nodes} - {first.node_id}

    informed = run.forecast(later, calm=calm)
    blind = run.forecast(later, calm=set())

    assert informed.speed_m_min < blind.speed_m_min


def test_probabilities_grow_with_the_horizon_and_export_as_geojson() -> None:
    truth = Truth(landscape())
    run, _ = start(truth, Wind(from_deg=270, speed_ms=6, source="test"))

    fc = run.forecast(T0 + timedelta(minutes=5), calm=set())
    p = {h: fc.probability(h) for h in (0, 15, 60, 120)}

    assert np.all(p[15] >= p[0] - 1e-9) and np.all(p[120] >= p[60] - 1e-9)
    data = fc.to_json()
    assert set(data["horizons"]) == {"0", "15", "30", "60", "120"}
    feats = data["horizons"]["60"]["features"]
    assert {f["properties"]["p"] for f in feats} <= {0.2, 0.5, 0.8} and feats
    lon, lat = feats[0]["geometry"]["coordinates"][0][0][:2]
    assert 8 < lon < 10 and 36 < lat < 38
    assert data["ignition"]["uncertainty_m"] >= 0
    assert data["next_nodes"] and data["next_nodes"][0]["eta_min"] >= 0


def test_demo_time_acceleration_scales_observed_intervals() -> None:
    truth = Truth(landscape())
    slow, order = start(truth, Wind(from_deg=270, speed_ms=6, source="test"))
    fast = SpreadRun(
        truth.ls, PHYS, CFG, order[0][1], T0, Wind(270, 6, "test"), truth.nodes, time_scale=60.0
    )
    t2, n2 = order[1]
    slow.observe(n2.node_id, "FIRE", T0 + timedelta(minutes=t2))
    fast.observe(n2.node_id, "FIRE", T0 + timedelta(seconds=t2))  # 60x faster

    a = slow.forecast(T0 + timedelta(minutes=t2 + 1), calm=set())
    b = fast.forecast(T0 + timedelta(seconds=t2 + 1), calm=set())

    assert a.heading_deg == pytest.approx(b.heading_deg, abs=1e-6)
