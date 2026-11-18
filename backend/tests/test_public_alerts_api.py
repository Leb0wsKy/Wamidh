from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from test_alerts import near_zone
from test_core import KEYS, SILENT, event
from wamidh_contracts import node_topic

from wamidh_backend.app import create_app
from wamidh_backend.core import Core, NodeInfo
from wamidh_backend.store import Store


class FakeZones:
    """Zone search without PostGIS (the real one is tested in tests/integration)."""

    def __init__(self, zones: list[dict[str, Any]]) -> None:
        self.zones = zones
        self.asked: list[tuple[float, float, float]] = []

    def zones_near(self, lon: float, lat: float, radius_km: float) -> list[dict[str, Any]]:
        self.asked.append((lon, lat, radius_km))
        return [z for z in self.zones if z["distance_km"] <= radius_km]

    def zones_geojson(self) -> dict[str, Any]:
        return {"type": "FeatureCollection", "features": [{"id": z["id"]} for z in self.zones]}

    def towers_geojson(self) -> dict[str, Any]:
        return {"type": "FeatureCollection", "features": []}


class RecordingBroadcast:
    exercise = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, list[str]]] = []

    def send(self, cap_xml: str, tower_ids: list[str]) -> str:
        self.sent.append((cap_xml, tower_ids))
        return "simulated"


ZONES = [
    near_zone(2, "عين دراهم", "عين دراهم", 900, 1.2, ["605-2-1-1"]),
    near_zone(5, None, "بلطة", 120, 2.5, ["605-2-1-1", "605-3-1-9"]),
]


def client(
    tmp_path: Path, zones: list[dict[str, Any]] = ZONES
) -> tuple[TestClient, Core, FakeZones, RecordingBroadcast]:
    core = Core(
        [NodeInfo(1, KEYS[1], 8.625, 36.709, 99.4, 35, None)],
        silent_after_s=SILENT,
        siren=lambda c, i: None,
    )
    placement = tmp_path / "placement"
    placement.mkdir()
    (placement / "gateways.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (placement / "risk.json").write_text("{}")
    source, radio = FakeZones(zones), RecordingBroadcast()
    app = create_app(
        core=core,
        store=Store(f"sqlite:///{tmp_path / 'eg.db'}"),
        placement_dir=placement,
        mqtt=None,
        zones_store=source,
        broadcast=radio,
    )
    return TestClient(app), core, source, radio


def fire(c: TestClient, core: Core) -> int:
    from test_api import T0

    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    return int(c.get("/api/v1/incidents").json()[0]["id"])


def test_zones_and_towers_are_public(tmp_path: Path) -> None:
    c, *_ = client(tmp_path)

    assert [f["id"] for f in c.get("/api/v1/zones").json()["features"]] == [2, 5]
    assert c.get("/api/v1/towers").json()["type"] == "FeatureCollection"


def test_proposal_for_the_incident_origin(tmp_path: Path) -> None:
    c, core, source, radio = client(tmp_path)
    inc = fire(c, core)

    p = c.get(f"/api/v1/incidents/{inc}/alert-proposal").json()

    assert source.asked == [(8.625, 36.709, 3.0)]  # the node, within concern_radius_km
    assert p["people"] == 1020 and p["tower_ids"] == ["605-2-1-1", "605-3-1-9"]
    assert [z["label"] for z in p["zones"]] == ["عين دراهم", "دوار قرب بلطة"]
    assert "outline" not in p["zones"][0]
    assert p["headline"].startswith("تحذير")
    assert radio.sent == []  # a proposal never broadcasts
    assert c.get("/api/v1/incidents/999/alert-proposal").status_code == 404


def test_alert_refused_before_ack(tmp_path: Path) -> None:
    c, core, _, radio = client(tmp_path)
    inc = fire(c, core)

    r = c.post(f"/api/v1/incidents/{inc}/alert", json={"confirmed_by": "dispatcher"})

    assert r.status_code == 409 and "acknowledge" in r.json()["detail"]
    assert radio.sent == []


def test_alert_refused_without_zones(tmp_path: Path) -> None:
    c, core, _, radio = client(tmp_path, zones=[])
    inc = fire(c, core)
    c.post(f"/api/v1/incidents/{inc}/ack")

    r = c.post(f"/api/v1/incidents/{inc}/alert", json={"confirmed_by": "dispatcher"})

    assert r.status_code == 409 and radio.sent == []


def test_alert_needs_who_confirmed(tmp_path: Path) -> None:
    c, core, _, _ = client(tmp_path)
    inc = fire(c, core)
    c.post(f"/api/v1/incidents/{inc}/ack")

    assert c.post(f"/api/v1/incidents/{inc}/alert", json={"confirmed_by": " "}).status_code == 422


def test_alert_sent_logged_and_public(tmp_path: Path) -> None:
    c, core, _, radio = client(tmp_path)
    inc = fire(c, core)
    c.post(f"/api/v1/incidents/{inc}/ack")

    sent = c.post(f"/api/v1/incidents/{inc}/alert", json={"confirmed_by": "dispatcher"}).json()

    ((xml, towers),) = radio.sent
    assert "<status>Exercise</status>" in xml and towers == ["605-2-1-1", "605-3-1-9"]
    assert sent["delivery"] == "simulated" and sent["status"] == "Exercise"
    assert sent["people"] == 1020 and sent["zone_ids"] == [2, 5]
    (audit,) = [e for e in core.list_incidents()[0].events if e.type == "public_alert"]
    assert audit.payload == {
        "alert_id": sent["id"],
        "zone_ids": [2, 5],
        "people": 1020,
        "confirmed_by": "dispatcher",
        "delivery": "simulated",
    }
    (public,) = c.get("/api/v1/alerts?active=true").json()
    assert public["incident_id"] == inc and public["message_ar"].startswith("تحذير")
    assert [z["label"] for z in public["zones"]] == ["عين دراهم", "دوار قرب بلطة"]
    assert set(public) == {
        "id", "incident_id", "created_at", "zones", "people", "headline", "message_ar",
        "status", "delivery", "active",
    }  # fmt: skip


def test_closed_incident_alerts_are_not_active(tmp_path: Path) -> None:
    c, core, _, _ = client(tmp_path)
    inc = fire(c, core)
    c.post(f"/api/v1/incidents/{inc}/ack")
    c.post(f"/api/v1/incidents/{inc}/alert", json={"confirmed_by": "dispatcher"})
    core._incidents[inc].status = "CLOSED"  # no crew in this app: close it directly

    assert c.get("/api/v1/alerts?active=true").json() == []
    (old,) = c.get("/api/v1/alerts").json()
    assert old["active"] is False
