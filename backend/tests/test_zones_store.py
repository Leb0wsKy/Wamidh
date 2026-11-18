from datetime import UTC, datetime
from pathlib import Path

import pytest
from shapely.geometry import MultiPolygon, Point, box, mapping

from wamidh_backend.store import Store

T0 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def zone(
    id_: int, lon: float, lat: float, people: int = 500, towers: list[str] | None = None
) -> dict:  # type: ignore[type-arg]
    d = 0.002  # ~200 m
    outline = MultiPolygon([box(lon - d, lat - d, lon + d, lat + d)])
    return {
        "id": id_,
        "name": f"village {id_}",
        "near": f"village {id_}",
        "population": people,
        "risk_level": "high",
        "risk_percentile": 85.0,
        "building_count": 40,
        "tower_ids": towers or [],
        "geometry": mapping(outline),
    }


def tower(id_: str, lon: float, lat: float) -> dict:  # type: ignore[type-arg]
    return {
        "id": id_,
        "radio": "LTE",
        "net": 2,
        "range_m": 1500,
        "samples": 12,
        "geometry": mapping(Point(lon, lat)),
    }


def test_zones_and_towers_are_served_as_geojson(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    store.replace_zones(
        [zone(1, 8.70, 36.80, towers=["605-2-1-1"])], [tower("605-2-1-1", 8.71, 36.80)]
    )

    zones = store.zones_geojson()
    towers = store.towers_geojson()

    (z,) = zones["features"]
    assert z["properties"]["id"] == 1 and z["properties"]["tower_ids"] == ["605-2-1-1"]
    assert z["geometry"]["type"] == "MultiPolygon"
    assert towers["features"][0]["properties"]["range_m"] == 1500
    assert towers["features"][0]["geometry"] == {"type": "Point", "coordinates": [8.71, 36.8]}


def test_replacing_zones_drops_the_previous_set(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    store.replace_zones([zone(1, 8.70, 36.80), zone(2, 8.75, 36.80)], [])
    store.replace_zones([zone(1, 8.70, 36.80)], [])

    assert [f["properties"]["id"] for f in store.zones_geojson()["features"]] == [1]


def test_zones_near_needs_postgresql(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match="PostgreSQL"):
        Store(f"sqlite:///{tmp_path / 'eg.db'}").zones_near(8.70, 36.80, 3)


def test_public_alert_round_trip(tmp_path: Path) -> None:
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")
    alert = {
        "incident_id": 7,
        "created_at": T0,
        "confirmed_by": "dispatcher",
        "zone_ids": [1, 2],
        "zone_labels": ["village 1", "village 2"],
        "tower_ids": ["605-2-1-1"],
        "people": 1200,
        "message_ar": "تحذير",
        "cap_xml": "<alert/>",
        "delivery": "simulated",
        "status": "Exercise",
    }

    alert_id = store.save_public_alert(alert)
    (loaded,) = store.list_public_alerts()

    assert loaded == {**alert, "id": alert_id}


def test_loader_reads_the_pipeline_outputs(tmp_path: Path) -> None:
    import json

    from wamidh_backend.load_zones import load

    out = tmp_path / "processed"
    out.mkdir()
    feature = lambda d: {"type": "Feature", "geometry": d.pop("geometry"), "properties": d}  # noqa: E731
    (out / "zones.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [feature(zone(1, 8.7, 36.8, towers=["605-2-1-1"]))],
            }
        ),
        encoding="utf-8",
    )
    (out / "towers.geojson").write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": [feature(tower("605-2-1-1", 8.71, 36.8))]}
        ),
        encoding="utf-8",
    )
    store = Store(f"sqlite:///{tmp_path / 'eg.db'}")

    counts = load(store, out)

    assert counts == {"zones": 1, "towers": 1, "links": 1}
    assert store.zones_geojson()["features"][0]["properties"]["tower_ids"] == ["605-2-1-1"]
