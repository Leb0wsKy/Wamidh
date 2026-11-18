from datetime import UTC, datetime, timedelta

from wamidh_sim.environment import SmokeEnvironment
from wamidh_sim.provision import build_registry

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


def test_smoke_ramps_up_linearly_then_holds() -> None:
    env = SmokeEnvironment()
    env.set_target(1.0, ramp_s=40, now=T0)

    assert env.level(T0) == 0.0
    assert env.level(T0 + timedelta(seconds=20)) == 0.5
    assert env.level(T0 + timedelta(seconds=60)) == 1.0


def test_extinguish_clears_the_air_at_once() -> None:
    env = SmokeEnvironment()
    env.set_target(1.0, ramp_s=0, now=T0)
    env.set_target(0.0, ramp_s=0, now=T0 + timedelta(seconds=5))

    assert env.level(T0 + timedelta(seconds=5)) == 0.0


def _nodes_geojson() -> dict:  # type: ignore[type-arg]
    feats = []
    for rank in [3, 1, 2]:
        feats.append(
            {
                "type": "Feature",
                "properties": {
                    "node_id": rank,
                    "rank": rank,
                    "risk_percentile": 99 - rank,
                    "gateway_id": 4,
                    "access_lon": 8.7,
                    "access_lat": 36.8,
                    "access_type": "track",
                },
                "geometry": {"type": "Point", "coordinates": [8.7 + rank / 100, 36.8]},
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def test_registry_installs_the_top_ranked_sites_each_with_its_own_key() -> None:
    reg = build_registry(_nodes_geojson(), count=2, base_port=8100, seed=1)

    assert [n["node_id"] for n in reg["nodes"]] == [1, 2]
    assert [n["control_port"] for n in reg["nodes"]] == [8101, 8102]
    keys = [n["key_hex"] for n in reg["nodes"]]
    assert len(set(keys)) == 2 and all(len(k) == 64 for k in keys)
    assert reg["nodes"][0]["access"] == {"lon": 8.7, "lat": 36.8, "road_type": "track"}


def test_growing_the_fleet_keeps_the_keys_of_nodes_already_installed() -> None:
    first = build_registry(_nodes_geojson(), count=2, base_port=8100, seed=1)

    grown = build_registry(_nodes_geojson(), count=3, base_port=8100, seed=2, existing=first)

    assert [n["node_id"] for n in grown["nodes"]] == [1, 2, 3]
    assert [n["key_hex"] for n in grown["nodes"][:2]] == [n["key_hex"] for n in first["nodes"]]
    assert grown["nodes"][2]["key_hex"] not in {n["key_hex"] for n in first["nodes"]}
