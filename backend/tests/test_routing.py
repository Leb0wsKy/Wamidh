import pytest
from shapely.geometry import LineString

from wamidh_backend.routing import RoadGraph

SPEEDS = {"primary": 60.0, "tertiary": 40.0, "track": 15.0}
# ~0.01 deg: 891 m east-west, 1112 m north-south at 36.8 N
P0, P1, P2 = (8.60, 36.80), (8.61, 36.80), (8.61, 36.81)


def graph(roads: list[tuple[list[tuple[float, float]], dict]]) -> RoadGraph:  # type: ignore[type-arg]
    lines = [LineString(coords) for coords, _ in roads]
    attrs = [
        {"fclass": "tertiary", "name": None, "ref": None, "oneway": "B", **a} for _, a in roads
    ]
    return RoadGraph.from_lines(lines, attrs, SPEEDS)


def test_route_follows_roads_and_reports_distance_and_time() -> None:
    g = graph([([P0, P1], {"fclass": "primary", "ref": "RN17"}), ([P1, P2], {"fclass": "track"})])

    r = g.route(P0, P2)

    assert r is not None
    assert r.distance_m == pytest.approx(891 + 1112, rel=0.01)
    assert r.duration_s == pytest.approx(891 / (60 / 3.6) + 1112 / (15 / 3.6), rel=0.01)
    assert r.geometry[0] == list(P0) and r.geometry[-1] == list(P2)


def test_steps_name_the_road_and_the_turn() -> None:
    g = graph([([P0, P1], {"fclass": "primary", "ref": "RN17"}), ([P1, P2], {"fclass": "track"})])

    steps = g.route(P0, P2).steps  # type: ignore[union-attr]

    assert [s.kind for s in steps] == ["depart", "left", "arrive"]
    assert steps[0].road == {"ref": "RN17", "name": None, "fclass": "primary"}
    assert steps[1].road["fclass"] == "track"
    assert steps[0].distance_m == pytest.approx(891, rel=0.01)


def test_prefers_the_faster_road_over_the_shorter_one() -> None:
    a, b = (8.60, 36.80), (8.62, 36.80)
    via = (8.61, 36.803)  # a detour north on a primary road
    g = graph(
        [
            ([a, b], {"fclass": "track"}),  # 1.8 km at 15 km/h = 7.2 min
            ([a, via, b], {"fclass": "primary"}),  # ~1.9 km at 60 km/h = 1.9 min
        ]
    )

    r = g.route(a, b)

    assert r is not None and r.steps[0].road["fclass"] == "primary"


def test_one_way_roads_are_not_driven_backwards() -> None:
    g = graph([([P0, P1], {"oneway": "F"})])

    assert g.route(P0, P1) is not None
    assert g.route(P1, P0) is None


def test_off_road_points_snap_to_the_nearest_road() -> None:
    g = graph([([P0, P1], {}), ([P1, P2], {})])

    r = g.route((8.60, 36.798), (8.612, 36.81))  # ~220 m south of P0, ~180 m east of P2

    assert r is not None
    assert r.geometry[0] == list(P0) and r.geometry[-1] == list(P2)


def test_missing_road_names_become_none_not_nan() -> None:
    g = graph([([P0, P1], {"name": float("nan"), "ref": float("nan")})])

    step = g.route(P0, P1).steps[0]  # type: ignore[union-attr]

    assert step.road["name"] is None and step.road["ref"] is None
