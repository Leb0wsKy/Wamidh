import math
import time

import numpy as np

from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics, arrival_times, length_to_breadth

PHYS = Physics(
    midflame_factor=0.4,
    max_length_to_breadth=8.0,
    upslope_coeff=0.069,
    downslope_coeff=0.035,
    horizon_limit_min=10_000,
)


def flat(n: int = 61, cell: float = 100.0, ros: float = 2.0) -> Landscape:
    return Landscape.uniform(n, n, cell, ros=ros)


def at(ls: Landscape, arrival: np.ndarray, di: int, dj: int) -> float:
    c = ls.rows // 2
    return float(arrival.reshape(ls.rows, ls.cols)[c + di, c + dj])


def test_no_wind_no_slope_spreads_in_a_circle_at_the_base_rate() -> None:
    ls = flat()
    centre = ls.index(ls.rows // 2, ls.cols // 2)

    t = arrival_times(ls, centre, PHYS, wind_from_deg=0, wind_ms=0, fuel_mult=1)

    # 2 km at 2 m/min = 1000 min, in every direction (16 neighbours keep the error small).
    for di, dj in [(0, 20), (20, 0), (14, 14), (-20, 0), (8, 18), (-18, -8)]:
        dist = math.hypot(di, dj) * 100
        assert abs(at(ls, t, di, dj) - dist / 2.0) / (dist / 2.0) < 0.06, (di, dj)


def test_wind_pushes_the_fire_downwind() -> None:
    ls = flat()
    centre = ls.index(ls.rows // 2, ls.cols // 2)

    # Wind FROM the west (270): the fire runs east.
    t = arrival_times(ls, centre, PHYS, wind_from_deg=270, wind_ms=8, fuel_mult=1)

    east, west, north = at(ls, t, 0, 10), at(ls, t, 0, -10), at(ls, t, -10, 0)
    head = 2.0 * math.exp(0.05039 * 8 * 3.6)
    assert abs(east - 1000 / head) / (1000 / head) < 0.06  # head rate: FBP wind function
    assert east < north < west  # the back may never arrive at all (inf)


def test_wind_exponent_strengthens_the_head_only() -> None:
    ls = flat()
    centre = ls.index(ls.rows // 2, ls.cols // 2)
    strong = Physics(0.4, 8.0, 0.069, 0.035, 10_000, wind_exponent=1.5)

    t = arrival_times(ls, centre, strong, wind_from_deg=270, wind_ms=8, fuel_mult=1)

    head = 2.0 * math.exp(0.05039 * 8 * 3.6 * 1.5)
    assert abs(at(ls, t, 0, 10) - 1000 / head) / (1000 / head) < 0.06


def test_length_to_breadth_follows_anderson() -> None:
    assert length_to_breadth(0.0) == 1.0
    # 0.936 e^(0.2566 U) + 0.461 e^(-0.1548 U) - 0.397, U midflame in mph (Finney 1998)
    assert abs(length_to_breadth(5.0) - 3.19) < 0.01
    assert length_to_breadth(2.0) < length_to_breadth(5.0)
    assert length_to_breadth(100.0) == 8.0  # capped


def test_fire_runs_faster_uphill() -> None:
    n = 61
    elevation = np.tile(np.arange(n, dtype=float)[::-1, None] * 10.0, (1, n))  # rises to the north
    ls = Landscape.uniform(n, n, 100.0, ros=2.0, elevation=elevation)
    centre = ls.index(n // 2, n // 2)

    t = arrival_times(ls, centre, PHYS, wind_from_deg=0, wind_ms=0, fuel_mult=1)

    up, down = at(ls, t, -15, 0), at(ls, t, 15, 0)  # north = uphill
    slope_deg = math.degrees(math.atan(10 / 100))
    assert abs(down / up - math.exp((0.069 + 0.035) * slope_deg)) < 0.25
    assert up < at(ls, t, 0, 15) < down


def test_water_is_a_barrier_except_through_a_gap() -> None:
    n = 41
    ros = np.full((n, n), 2.0)
    ros[:, 25] = 0.0  # a river north-south ...
    ros[5, 25] = 2.0  # ... with one ford in the north
    ls = Landscape.from_arrays(ros, 100.0)
    centre = ls.index(20, 20)

    t = arrival_times(ls, centre, PHYS, wind_from_deg=0, wind_ms=0, fuel_mult=1).reshape(n, n)

    assert np.isinf(t[20, 25])  # the river itself never burns
    straight = 10 * 100 / 2.0
    assert t[20, 30] > straight * 1.5  # across the river: around through the ford


def test_one_arrival_map_is_fast_enough_for_an_ensemble() -> None:
    ls = flat(n=120)
    centre = ls.index(60, 60)
    arrival_times(ls, centre, PHYS, wind_from_deg=270, wind_ms=6, fuel_mult=1)  # warm caches

    start = time.perf_counter()
    for _ in range(10):
        arrival_times(ls, centre, PHYS, wind_from_deg=270, wind_ms=6, fuel_mult=1)
    per_member = (time.perf_counter() - start) / 10

    assert per_member < 0.08  # 200 members in a few seconds on a laptop
