import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from wamidh_backend.core import Incident, IncidentEvent
from wamidh_backend.db import upgrade
from wamidh_backend.migrate_sqlite import migrate
from wamidh_backend.store import Store

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


def _incident(id_: int, events: int) -> Incident:
    return Incident(
        id=id_,
        status="CLOSED",
        first_node_id=1,
        estimated_origin={"lon": 8.6 + id_ / 100, "lat": 36.7},
        created_at=T0,
        access_point={"lon": 8.61, "lat": 36.71, "road_type": "track"},
        node_ids={1, 2},
        assigned_crew=1,
        acknowledged_at=T0 + timedelta(seconds=30),
        events=[
            IncidentEvent(T0 + timedelta(seconds=k), "node_fire", {"node_id": 1})
            for k in range(events)
        ],
    )


def _source(tmp_path: Path) -> str:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    store = Store(url)
    store.save_incident(_incident(3, events=3))
    store.save_incident(_incident(4, events=2))
    base = {"seq": 0, "ts": "x", "gas_ratio": 1.0, "temp_c": 30.0, "rh_pct": 40.0}
    base |= {"flame": False, "fire_prob": 0.5, "battery_v": 4.0, "node_id": 1, "state": "NORMAL"}
    for k in range(7):
        store.save_telemetry({**base, "seq": k}, T0 + timedelta(seconds=10 * k))
    return url


def _count(url: str, table: str) -> int:
    with create_engine(url).connect() as c:
        return int(c.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)


def test_copies_incidents_logs_and_telemetry(tmp_path: Path, pg_url: str) -> None:
    src = _source(tmp_path)
    upgrade(pg_url)

    counts = migrate(src, pg_url)

    assert counts == {"incident": 2, "incident_event": 5, "telemetry": 7}
    assert [i.to_json() for i in Store(pg_url).load_incidents()] == [
        i.to_json() for i in Store(src).load_incidents()
    ]
    assert _count(pg_url, "incident WHERE origin IS NOT NULL") == 2
    assert Store(pg_url).incidents_near(8.63, 36.7, 2) == [3, 4]  # origins are real points


def test_refuses_a_non_empty_target_unless_forced(tmp_path: Path, pg_url: str) -> None:
    src = _source(tmp_path)
    upgrade(pg_url)
    migrate(src, pg_url)

    with pytest.raises(SystemExit, match="already holds"):
        migrate(src, pg_url)
    assert migrate(src, pg_url, force=True)["incident"] == 2
    assert _count(pg_url, "incident") == 2  # replaced, not duplicated


def test_new_rows_after_migration_get_fresh_ids(tmp_path: Path, pg_url: str) -> None:
    src = _source(tmp_path)
    upgrade(pg_url)
    migrate(src, pg_url)
    store = Store(pg_url)

    store.save_telemetry(
        {
            "seq": 99,
            "ts": "x",
            "gas_ratio": 1.0,
            "temp_c": 30.0,
            "rh_pct": 40.0,
            "flame": False,
            "fire_prob": 0.1,
            "battery_v": 4.0,
            "node_id": 1,
            "state": "NORMAL",
        },
        T0 + timedelta(hours=1),
    )
    store.save_incident(_incident(5, events=1))

    assert _count(pg_url, "telemetry") == 8 and _count(pg_url, "incident_event") == 6


def test_source_file_is_not_modified(tmp_path: Path, pg_url: str) -> None:
    src = _source(tmp_path)
    path = Path(src.removeprefix("sqlite:///"))
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    upgrade(pg_url)

    migrate(src, pg_url)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
