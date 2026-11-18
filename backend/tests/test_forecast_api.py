from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from test_core import KEYS, SILENT, event
from test_spread_service import NODES, FixedWind, FlatEngine
from wamidh_contracts import node_topic

from wamidh_backend.app import create_app
from wamidh_backend.core import Core, NodeInfo
from wamidh_backend.spread_service import SpreadService
from wamidh_backend.store import Store
from wamidh_backend.weather import WeatherService

WEATHER = {"from_deg": 0, "speed_ms": 0}


def client(tmp_path: Path, with_spread: bool = True) -> tuple[TestClient, Core]:
    first = NODES[0]
    core = Core(
        [NodeInfo(1, KEYS[1], first.lon, first.lat, 99.0, None, None)],
        silent_after_s=SILENT,
        siren=lambda c, i: None,
    )
    placement = tmp_path / "placement"
    placement.mkdir()
    (placement / "gateways.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (placement / "risk.json").write_text("{}")
    weather = WeatherService(FixedWind(), cache_s=600, default=WEATHER)
    spread = SpreadService(FlatEngine(), weather, NODES) if with_spread else None
    app = create_app(
        core=core,
        store=Store(f"sqlite:///{tmp_path / 'eg.db'}"),
        placement_dir=placement,
        mqtt=None,
        weather=weather,
        spread=spread,
    )
    return TestClient(app), core


def fire(c: TestClient, core: Core) -> int:
    from test_api import T0

    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0 + timedelta(seconds=0))
    return int(c.get("/api/v1/incidents").json()[0]["id"])


def test_forecast_of_an_incident(tmp_path: Path) -> None:
    c, core = client(tmp_path)
    inc = fire(c, core)

    fc = c.get(f"/api/v1/incidents/{inc}/forecast").json()

    assert fc["incident_id"] == inc and fc["advisory"] is True
    assert set(fc["horizons"]) == {"0", "15", "30", "60", "120"}
    assert fc["wind_reading"]["source"] == "openweathermap"
    assert c.get("/api/v1/incidents/999/forecast").status_code == 404


def test_forecast_needs_the_spread_engine(tmp_path: Path) -> None:
    c, core = client(tmp_path, with_spread=False)
    inc = fire(c, core)

    assert c.get(f"/api/v1/incidents/{inc}/forecast").status_code == 503


def test_wind_now_at_a_point(tmp_path: Path) -> None:
    c, _ = client(tmp_path)

    w = c.get("/api/v1/weather", params={"lat": 36.8, "lon": 8.7}).json()

    assert (w["from_deg"], w["speed_ms"], w["source"]) == (270.0, 6.0, "openweathermap")
    assert c.get("/api/v1/weather", params={"lat": 120, "lon": 8.7}).status_code == 422
