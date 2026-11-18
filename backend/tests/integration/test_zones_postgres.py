from test_zones_store import tower, zone

from wamidh_backend.db import upgrade
from wamidh_backend.store import Store

LON, LAT = 8.70, 36.80


def test_zones_near_order_and_radius(pg_url: str) -> None:
    upgrade(pg_url)
    store = Store(pg_url)
    # Zones ~1, 2.5 and 8 km north of the fire (1 degree of latitude ~ 111.2 km).
    store.replace_zones(
        [
            zone(1, LON, LAT + 8 / 111.2, people=300),
            zone(2, LON, LAT + 1 / 111.2, people=900, towers=["605-2-1-1"]),
            zone(3, LON, LAT + 2.5 / 111.2, people=400),
        ],
        [tower("605-2-1-1", LON, LAT + 1 / 111.2)],
    )

    near = store.zones_near(LON, LAT, 3)

    assert [z["id"] for z in near] == [2, 3]  # nearest first, the 8 km zone left out
    assert near[0]["tower_ids"] == ["605-2-1-1"] and near[0]["population"] == 900
    assert 0.6 < near[0]["distance_km"] < 1.0  # distance to the zone edge, not its centre


def test_loaded_zones_survive_a_new_store(pg_url: str) -> None:
    upgrade(pg_url)
    Store(pg_url).replace_zones([zone(1, LON, LAT)], [tower("605-2-1-1", LON, LAT)])

    store = Store(pg_url)

    assert len(store.zones_geojson()["features"]) == 1
    assert len(store.towers_geojson()["features"]) == 1
