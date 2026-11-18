import numpy as np
from pyproj import Transformer
from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics, arrival_times

from wamidh_sim.scenario import plan

TO_LONLAT = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
X0, Y0 = 470_000.0, 4_080_000.0
PHYS = Physics(0.4, 8, 0.069, 0.035, 600)


def sensor(node_id: int, x: float, y: float) -> dict:  # type: ignore[type-arg]
    lon, lat = TO_LONLAT.transform(x, y)
    return {"node_id": node_id, "lon": lon, "lat": lat, "control_port": 8100 + node_id}


def test_the_hidden_fire_reaches_sensors_downwind_in_order_and_burns_them() -> None:
    ls = Landscape.from_arrays(np.full((60, 60), 3.0), 100.0, x0=X0, y0=Y0)
    ignition = ls.index(30, 10)
    arrival = arrival_times(ls, ignition, PHYS, wind_from_deg=270, wind_ms=6, fuel_mult=1)
    # Three sensors on the fire's line (east), one far upwind.
    nodes = [
        sensor(1, X0 + 1250, Y0 - 3050),
        sensor(2, X0 + 2250, Y0 - 3050),
        sensor(3, X0 + 3250, Y0 - 3050),
        sensor(4, X0 + 50, Y0 - 50),
    ]

    steps = plan(ls, arrival, nodes, detect_radius_m=300, burn_min=20, until_min=600)

    ignites = [(s.node_id, s.fire_min) for s in steps if s.action == "ignite"]
    assert [n for n, _ in ignites] == [1, 2, 3]
    assert ignites[0][1] == 0  # the schedule starts at the first detection
    assert ignites[1][1] < ignites[2][1]
    lost = {s.node_id: s.fire_min for s in steps if s.action == "burn"}
    assert lost[1] > ignites[0][1]  # each sensor burns after detecting
    assert all(a.fire_min <= b.fire_min for a, b in zip(steps, steps[1:], strict=False))


def test_nothing_happens_beyond_the_horizon() -> None:
    ls = Landscape.from_arrays(np.full((60, 60), 3.0), 100.0, x0=X0, y0=Y0)
    arrival = arrival_times(ls, ls.index(30, 10), PHYS, 270, 6, 1)
    nodes = [sensor(1, X0 + 1250, Y0 - 3050), sensor(3, X0 + 5250, Y0 - 3050)]

    steps = plan(ls, arrival, nodes, detect_radius_m=300, burn_min=20, until_min=200)

    assert {s.node_id for s in steps} == {1}
