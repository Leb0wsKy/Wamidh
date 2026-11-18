from datetime import UTC, datetime, timedelta

import pytest

from wamidh_backend.core import Incident, IncidentEvent
from wamidh_backend.store import Store

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


def test_incidents_survive_a_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'eg.db'}"
    inc = Incident(
        id=1,
        status="ACKNOWLEDGED",
        first_node_id=3,
        estimated_origin={"lon": 8.6, "lat": 36.7},
        created_at=T0,
        access_point={"lon": 8.61, "lat": 36.71, "road_type": "track"},
        acknowledged_at=T0,
        node_ids={3, 4},
        assigned_crew=2,
        events=[
            IncidentEvent(T0, "node_fire", {"node_id": 3}),
            IncidentEvent(T0, "acknowledged", {}),
        ],
    )
    Store(url).save_incident(inc)

    (loaded,) = Store(url).load_incidents()

    assert loaded.to_json() == inc.to_json()
    assert loaded.node_ids == {3, 4}


def test_telemetry_rows_are_appended(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    for seq in range(3):
        store.save_telemetry(
            {
                "node_id": 1,
                "seq": seq,
                "ts": "2026-07-20T14:00:00Z",
                "state": "NORMAL",
                "gas_ratio": 1.0,
                "temp_c": 30.0,
                "rh_pct": 40.0,
                "flame": False,
                "fire_prob": 0.02,
                "battery_v": 4.0,
            },
            received_at=T0,
        )

    assert store.count_telemetry(1) == 3


def test_recent_telemetry_per_node_in_time_order(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    reading = {
        "seq": 0,
        "ts": "2026-07-20T14:00:00Z",
        "gas_ratio": 1.0,
        "temp_c": 30.0,
        "rh_pct": 40.0,
        "flame": False,
        "fire_prob": 0.03,
        "battery_v": 4.0,
    }
    store.save_telemetry({**reading, "node_id": 1, "state": "NORMAL"}, T0)
    store.save_telemetry({**reading, "node_id": 1, "state": "ALERT"}, T0 + timedelta(minutes=2))
    store.save_telemetry({**reading, "node_id": 2, "state": "NORMAL"}, T0 - timedelta(hours=2))

    recent = store.telemetry_since(T0 - timedelta(minutes=1))

    assert list(recent) == [1]  # node 2's reading is too old
    assert [p["state"] for p in recent[1]] == ["NORMAL", "ALERT"]
    assert recent[1][0] == {
        "ts": "2026-07-20T14:00:00Z",
        "state": "NORMAL",
        "temp_c": 30.0,
        "rh_pct": 40.0,
        "gas_ratio": 1.0,
        "fire_prob": 0.03,
        "battery_v": 4.0,
    }


def test_node_memory_survives_a_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'eg.db'}"
    store = Store(url)
    base = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0}
    base |= {"flame": False, "fire_prob": 0.5, "battery_v": 4.0, "node_id": 1}
    store.save_telemetry({**base, "state": "ALERT"}, T0)
    store.save_telemetry({**base, "state": "FIRE"}, T0 + timedelta(minutes=1))
    store.save_telemetry({**base, "state": "ALERT"}, T0 + timedelta(minutes=2))
    store.save_telemetry({**base, "state": "NORMAL"}, T0 + timedelta(minutes=3))

    mem = Store(url).node_memory()  # a fresh Store, as after a restart

    assert mem == {1: {"ALERT": T0 + timedelta(minutes=2), "FIRE": T0 + timedelta(minutes=1)}}


def _incident(origin: dict) -> Incident:  # type: ignore[type-arg]
    return Incident(
        id=9,
        status="NEW",
        first_node_id=1,
        estimated_origin=origin,
        created_at=T0,
        access_point=None,
        node_ids={1},
        events=[IncidentEvent(T0, "node_fire", {"node_id": 1})],
    )


def _origin_column(url: str) -> object:
    from sqlalchemy import create_engine, text

    with create_engine(url).connect() as c:
        return c.execute(text("SELECT origin FROM incident WHERE id = 9")).scalar()


def test_the_incident_origin_is_stored_as_a_point(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'eg.db'}"
    Store(url).save_incident(_incident({"lon": 8.625, "lat": 36.709}))

    assert _origin_column(url) == "SRID=4326;POINT(8.625 36.709)"


def test_incident_without_origin_saves(tmp_path) -> None:  # type: ignore[no-untyped-def]
    url = f"sqlite:///{tmp_path / 'eg.db'}"
    Store(url).save_incident(_incident({}))

    assert _origin_column(url) is None
    assert Store(url).load_incidents()[0].estimated_origin == {}


def test_distance_search_needs_postgresql(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(NotImplementedError, match="PostgreSQL"):
        Store(f"sqlite:///{tmp_path / 'eg.db'}").incidents_near(8.6, 36.7, 5)
