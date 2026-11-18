from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from shapely.geometry import LineString
from test_core import KEYS, SILENT, event, telemetry
from wamidh_contracts import node_topic

from wamidh_backend.app import create_app
from wamidh_backend.core import Core, NodeInfo
from wamidh_backend.routing import RoadGraph
from wamidh_backend.store import Store

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
CREWS = [
    {"id": 1, "name": "Équipe 1", "station_id": 1},
    {"id": 2, "name": "Équipe 2", "station_id": 1},
]
STATIONS = [{"id": 1, "name": "Protection civile Tabarka", "lon": 8.787, "lat": 36.946}]


def client(tmp_path, router=None, access=None) -> tuple[TestClient, Core]:  # type: ignore[no-untyped-def]
    sirens: list[tuple[str, int]] = []
    core = Core(
        [NodeInfo(1, KEYS[1], 8.625, 36.709, 99.4, 35, access)],
        silent_after_s=SILENT,
        siren=lambda c, i: sirens.append((c, i)),
    )
    placement = tmp_path / "placement"
    placement.mkdir()
    (placement / "gateways.geojson").write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":'
        '{"gateway_id":35,"elevation_m":900.0,"nodes_assigned":4},'
        '"geometry":{"type":"Point","coordinates":[8.63,36.72]}}]}'
    )
    (placement / "risk.json").write_text('{"url":"/placement/risk.png","bounds":[[36,8],[37,9]]}')
    app = create_app(
        core=core,
        store=Store(f"sqlite:///{tmp_path / 'eg.db'}"),
        placement_dir=placement,
        mqtt=None,
        crews=CREWS,
        stations=STATIONS,
        router=router,
    )
    return TestClient(app), core


def test_nodes_gateways_and_risk_map(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0), T0)

    nodes = c.get("/api/v1/nodes").json()
    assert nodes[0]["id"] == 1 and nodes[0]["state"] == "NORMAL"
    assert nodes[0]["link"] == {"received": 1, "lost": 0, "rejected": 0}
    assert c.get("/api/v1/gateways").json() == [
        {"id": 35, "lon": 8.63, "lat": 36.72, "elevation_m": 900.0, "nodes_assigned": 4}
    ]
    assert c.get("/api/v1/risk-map").json()["url"] == "/placement/risk.png"


def test_acknowledge_and_crew_status_over_http(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path)
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    (inc,) = c.get("/api/v1/incidents").json()

    acked = c.post(f"/api/v1/incidents/{inc['id']}/ack").json()
    assert acked["status"] == "ACKNOWLEDGED"

    taken = c.post(f"/api/v1/incidents/{inc['id']}/assign", json={"crew_id": 1}).json()
    assert taken["assigned_crew"] == 1
    other = c.post(f"/api/v1/incidents/{inc['id']}/assign", json={"crew_id": 2})
    assert other.status_code == 409

    wrong_crew = c.post(
        f"/api/v1/incidents/{inc['id']}/status", json={"status": "EN_ROUTE", "crew_id": 2}
    )
    assert wrong_crew.status_code == 409
    ok = c.post(f"/api/v1/incidents/{inc['id']}/status", json={"status": "EN_ROUTE", "crew_id": 1})
    assert ok.json()["status"] == "EN_ROUTE"


def test_crews_and_stations(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = client(tmp_path)

    assert c.get("/api/v1/crews").json() == CREWS
    assert c.get("/api/v1/stations").json() == STATIONS


def test_websocket_pushes_changes_to_dashboards(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path)
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    inc_id = core.list_incidents()[0].id

    with c.websocket_connect("/api/v1/ws") as ws:
        c.post(f"/api/v1/incidents/{inc_id}/ack")
        msg = ws.receive_json()

    assert msg["kind"] == "incident" and msg["incident"]["status"] == "ACKNOWLEDGED"


def test_nodes_carry_their_coverage_zone_radius(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = client(tmp_path)

    assert c.get("/api/v1/nodes").json()[0]["coverage_radius_m"] == 500


# A tiny road network: station at the east end, node 1 just north of the west end.
ROADS = RoadGraph.from_lines(
    [LineString([(8.787, 36.946), (8.70, 36.80)]), LineString([(8.70, 36.80), (8.625, 36.708)])],
    [
        {"fclass": "primary", "ref": "RN17", "name": None, "oneway": "B"},
        {"fclass": "track", "ref": None, "name": None, "oneway": "B"},
    ],
    {"primary": 60.0, "track": 15.0},
)
ACCESS = {"lon": 8.625, "lat": 36.708, "road_type": "track"}


def fire(c: TestClient, core: Core) -> int:
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    return int(c.get("/api/v1/incidents").json()[0]["id"])


def test_route_from_the_crew_station_to_the_access_point_then_walk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path, router=ROADS, access=ACCESS)
    iid = fire(c, core)

    r = c.get(f"/api/v1/incidents/{iid}/route", params={"crew_id": 1}).json()

    assert r["origin"] == {"lon": 8.787, "lat": 36.946, "source": "station"}
    assert r["drive"]["geometry"][0] == [8.787, 36.946]
    assert r["drive"]["geometry"][-1] == [8.625, 36.708]
    assert r["drive"]["steps"][-1]["kind"] == "arrive"
    assert r["walk"]["geometry"] == [[8.625, 36.708], [8.625, 36.709]]
    assert 100 < r["walk"]["distance_m"] < 120
    assert r["target"] == {"node_id": 1, "lon": 8.625, "lat": 36.709}


def test_route_from_a_live_gps_position(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path, router=ROADS, access=ACCESS)
    iid = fire(c, core)

    r = c.get(f"/api/v1/incidents/{iid}/route", params={"from": "36.80,8.70"}).json()

    assert r["origin"]["source"] == "gps"
    assert r["drive"]["geometry"][0] == [8.70, 36.80]


def test_route_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path, router=ROADS, access=ACCESS)
    iid = fire(c, core)
    assert c.get("/api/v1/incidents/99/route").status_code == 404
    assert c.get(f"/api/v1/incidents/{iid}/route", params={"from": "nope"}).status_code == 422

    (tmp_path / "b").mkdir()
    c2, core2 = client(tmp_path / "b", access=ACCESS)
    assert c2.get(f"/api/v1/incidents/{fire(c2, core2)}/route").status_code == 503


def test_history_of_every_installed_sensor(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path)
    now = datetime.now(UTC)
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    reading = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0}
    reading |= {"flame": False, "fire_prob": 0.03, "battery_v": 4.0, "node_id": 1}
    for k, state in enumerate(["NORMAL", "ALERT", "FIRE"]):
        store.save_telemetry({**reading, "state": state}, now - timedelta(minutes=30 - k))
    store.save_telemetry({**reading, "state": "NORMAL"}, now - timedelta(hours=3))

    h = c.get("/api/v1/history", params={"minutes": 60}).json()

    assert h["silent_after_s"] == SILENT
    assert [n["node_id"] for n in h["nodes"]] == [1]
    assert [p["state"] for p in h["nodes"][0]["points"]] == ["NORMAL", "ALERT", "FIRE"]
    assert c.get("/api/v1/history", params={"minutes": 0}).status_code == 422


def test_nodes_expose_alarm_history_and_access_point(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, core = client(tmp_path, access=ACCESS)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT"), T0)

    n = c.get("/api/v1/nodes").json()[0]
    assert n["last_alert_at"] == "2026-07-20T14:00:00Z" and n["last_fire_at"] is None
    assert n["access_point"] == ACCESS


def test_near_validation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = client(tmp_path)

    for params in (
        {"near": "abc"},
        {"near": "36.7,8.6", "radius_km": 0},
        {"near": "36.7,8.6", "radius_km": 500},
    ):
        assert c.get("/api/v1/incidents", params=params).status_code == 422


def test_near_needs_postgresql(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = client(tmp_path)

    r = c.get("/api/v1/incidents", params={"near": "36.7,8.6", "radius_km": 5})

    assert r.status_code == 501 and "PostgreSQL" in r.json()["detail"]


def test_history_of_chosen_sensors_only(tmp_path) -> None:  # type: ignore[no-untyped-def]
    c, _ = client(tmp_path)
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    reading = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0}
    reading |= {"flame": False, "fire_prob": 0.03, "battery_v": 4.0, "state": "NORMAL"}
    now = datetime.now(UTC)
    for node_id in (1, 2):
        store.save_telemetry({**reading, "node_id": node_id}, now - timedelta(minutes=5))

    assert store.telemetry_since(now - timedelta(hours=1), node_ids=[2]).keys() == {2}
    one = c.get("/api/v1/history", params={"minutes": 60, "nodes": "1"}).json()
    assert [n["node_id"] for n in one["nodes"]] == [1]
    assert c.get("/api/v1/history", params={"nodes": "5"}).json()["nodes"] == []
    assert c.get("/api/v1/history", params={"nodes": "1,x"}).status_code == 422
