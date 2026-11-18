from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from wamidh_backend.app import create_app
from wamidh_backend.core import Core, Incident, IncidentEvent, NodeInfo
from wamidh_backend.db import schema_is_current, upgrade
from wamidh_backend.store import Store

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
LON, LAT = 8.70, 36.80
# ~1, 4 and 9 km due north of (LON, LAT): 1 degree of latitude is ~111.2 km.
OFFSETS_KM = {11: 1.0, 12: 4.0, 13: 9.0}


def incident(id_: int, lon: float, lat: float, events: int = 1) -> Incident:
    return Incident(
        id=id_,
        status="CLOSED",
        first_node_id=1,
        estimated_origin={"lon": lon, "lat": lat},
        created_at=T0,
        access_point=None,
        node_ids={1},
        events=[
            IncidentEvent(T0 + timedelta(seconds=k), "node_fire", {"node_id": 1})
            for k in range(events)
        ],
    )


def test_store_refuses_an_unmigrated_schema(pg_url: str) -> None:
    assert not schema_is_current(pg_url)
    with pytest.raises(SystemExit, match="upgrade"):
        Store(pg_url)


def test_migrations_create_the_schema_with_postgis(pg_url: str) -> None:
    upgrade(pg_url)

    assert schema_is_current(pg_url)
    engine = create_engine(pg_url)
    insp = inspect(engine)
    assert {"telemetry", "incident", "incident_event"} <= set(insp.get_table_names())
    with engine.connect() as c:
        kind = c.execute(
            text(
                "SELECT udt_name FROM information_schema.columns WHERE table_name='incident'"
                " AND column_name='origin' AND table_schema=current_schema()"
            )
        ).scalar()
        index = c.execute(
            text(
                "SELECT indexdef FROM pg_indexes WHERE indexname='ix_incident_origin'"
                " AND schemaname=current_schema()"
            )
        ).scalar()
    assert kind == "geography"
    assert index is not None and "gist" in index.lower()


def test_incidents_and_logs_survive_a_new_store(pg_url: str) -> None:
    upgrade(pg_url)
    Store(pg_url).save_incident(incident(5, LON, LAT, events=3))

    (loaded,) = Store(pg_url).load_incidents()

    assert loaded.to_json() == incident(5, LON, LAT, events=3).to_json()


def test_telemetry_history(pg_url: str) -> None:
    upgrade(pg_url)
    store = Store(pg_url)
    base = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0}
    base |= {"flame": False, "fire_prob": 0.5, "battery_v": 4.0, "node_id": 1}
    store.save_telemetry({**base, "state": "ALERT"}, T0)
    store.save_telemetry({**base, "state": "FIRE"}, T0 + timedelta(minutes=1))

    assert [p["state"] for p in store.telemetry_since(T0 - timedelta(minutes=1))[1]] == [
        "ALERT",
        "FIRE",
    ]
    assert store.node_memory() == {1: {"ALERT": T0, "FIRE": T0 + timedelta(minutes=1)}}


def _three_incidents(store: Store) -> None:
    for id_, km in OFFSETS_KM.items():
        store.save_incident(incident(id_, LON, LAT + km / 111.2))


def test_incidents_near_in_distance_order(pg_url: str) -> None:
    upgrade(pg_url)
    store = Store(pg_url)
    _three_incidents(store)

    assert store.incidents_near(LON, LAT, 5) == [11, 12]
    assert store.incidents_near(LON, LAT, 0.5) == []


def test_api_near_on_postgres(pg_url: str) -> None:
    upgrade(pg_url)
    store = Store(pg_url)
    _three_incidents(store)
    core = Core(
        [NodeInfo(1, b"k" * 32, LON, LAT, 99.0, None, None)],
        silent_after_s={"NORMAL": 40, "ALERT": 20, "FIRE": 10},
        siren=lambda *_: None,
    )
    import tempfile
    from pathlib import Path

    placement = Path(tempfile.mkdtemp())
    (placement / "gateways.geojson").write_text('{"type":"FeatureCollection","features":[]}')
    (placement / "risk.json").write_text('{"url":"x","bounds":[[0,0],[1,1]]}')
    c = TestClient(create_app(core=core, store=store, placement_dir=placement, mqtt=None))

    r = c.get("/api/v1/incidents", params={"near": f"{LAT},{LON}", "radius_km": 5})

    assert r.status_code == 200 and [i["id"] for i in r.json()] == [11, 12]


def test_isolated_from_development_data(pg_url: str) -> None:
    # A test must never see (let alone write) the real tables: before its own migration, no
    # Wamidh table may be visible on its search path.
    with create_engine(pg_url).connect() as c:
        visible = c.execute(
            text(
                "SELECT to_regclass('incident'), to_regclass('telemetry'),"
                " to_regclass('alembic_version')"
            )
        ).one()
    assert visible == (None, None, None)
