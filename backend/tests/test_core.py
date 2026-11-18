import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from wamidh_contracts import node_topic, sign

from wamidh_backend.core import Core, NodeInfo

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
KEYS = {1: b"a" * 32, 2: b"b" * 32}
SILENT = {"NORMAL": 40, "ALERT": 20, "FIRE": 10}


class FakeSiren:
    def __init__(self) -> None:
        self.commands: list[tuple[str, int]] = []

    def __call__(self, command: str, incident_id: int) -> None:
        self.commands.append((command, incident_id))


def make_core() -> tuple[Core, FakeSiren]:
    siren = FakeSiren()
    nodes = [
        NodeInfo(
            1,
            KEYS[1],
            lon=8.625,
            lat=36.709,
            risk_percentile=99.4,
            gateway_id=35,
            access={"lon": 8.626, "lat": 36.71, "road_type": "residential"},
        ),
        NodeInfo(
            2, KEYS[2], lon=8.630, lat=36.715, risk_percentile=99.3, gateway_id=31, access=None
        ),
    ]
    return Core(nodes, silent_after_s=SILENT, siren=siren), siren


def telemetry(
    node_id: int, seq: int, state: str = "NORMAL", key: bytes | None = None, **extra: Any
) -> bytes:
    body = {
        "node_id": node_id,
        "seq": seq,
        "ts": "2026-07-20T14:00:00Z",
        "state": state,
        "gas_ratio": 1.0,
        "temp_c": 31.0,
        "rh_pct": 30.0,
        "flame": False,
        "fire_prob": 0.03,
        "battery_v": 4.0,
        **extra,
    }
    return json.dumps({**body, "sig": sign(body, key or KEYS[node_id])}).encode()


def event(node_id: int, seq: int, frm: str, to: str) -> bytes:
    body = {
        "node_id": node_id,
        "seq": seq,
        "ts": "2026-07-20T14:00:00Z",
        "from_state": frm,
        "to_state": to,
        "fire_prob": 0.95,
        "flame": True,
    }
    return json.dumps({**body, "sig": sign(body, KEYS[node_id])}).encode()


# --- ingest -------------------------------------------------------------------------


def test_nodes_start_unknown_until_they_report() -> None:
    core, _ = make_core()

    assert [n.state for n in core.list_nodes()] == ["OFFLINE", "OFFLINE"]


def test_valid_telemetry_updates_the_node() -> None:
    core, _ = make_core()

    out = core.handle(node_topic(1, "telemetry"), telemetry(1, 0), T0)

    node = core.node(1)
    assert node.state == "NORMAL" and node.last_seen == T0 and node.battery_v == 4.0
    assert [e["kind"] for e in out] == ["node"]


@pytest.mark.parametrize(
    "payload",
    [
        telemetry(1, 0, key=b"wrong-key"),  # forged
        telemetry(2, 0),  # node 2's message on node 1's topic
        b"not json",
        json.dumps({"node_id": 1, "seq": 0}).encode(),  # unsigned, incomplete
    ],
)
def test_invalid_messages_are_rejected_and_counted(payload: bytes) -> None:
    core, _ = make_core()

    out = core.handle(node_topic(1, "telemetry"), payload, T0)

    assert out == []
    assert core.node(1).state == "OFFLINE"
    assert core.stats(1)["rejected"] == 1


def test_unknown_node_is_ignored() -> None:
    core, _ = make_core()

    assert core.handle(node_topic(99, "telemetry"), telemetry(1, 0), T0) == []


def test_duplicates_are_dropped_and_gaps_count_as_lost_packets() -> None:
    core, _ = make_core()
    for seq in [0, 1, 1, 4]:  # 1 is redelivered; 2 and 3 never arrive
        core.handle(node_topic(1, "telemetry"), telemetry(1, seq), T0)

    assert core.stats(1) == {"received": 3, "lost": 2, "rejected": 0}


# --- incidents -----------------------------------------------------------------------


def test_first_fire_opens_an_incident_and_sounds_the_siren() -> None:
    core, siren = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0), T0)

    out = core.handle(node_topic(1, "event"), event(1, 1, "ALERT", "FIRE"), T0)

    (inc,) = core.list_incidents()
    assert inc.status == "STATION_NOTIFIED" and inc.first_node_id == 1
    assert inc.access_point == {"lon": 8.626, "lat": 36.71, "road_type": "residential"}
    assert [e.type for e in inc.events] == ["node_fire", "station_notified"]
    assert siren.commands == [("on", inc.id)]
    assert core.node(1).state == "FIRE"
    assert {e["kind"] for e in out} == {"node", "incident"}


def test_spread_to_a_neighbour_while_the_fire_burns_joins_the_same_incident() -> None:
    core, siren = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)

    core.handle(node_topic(2, "event"), event(2, 0, "ALERT", "FIRE"), T0 + timedelta(minutes=5))

    (inc,) = core.list_incidents()
    assert [e.type for e in inc.events][-1] == "fire_spread"
    assert inc.events[-1].payload["node_id"] == 2
    assert len(siren.commands) == 1


def test_a_new_fire_after_the_previous_one_is_out_opens_a_new_incident() -> None:
    # The bug seen live: a fire near an old, acknowledged but extinguished incident was
    # silently attached to it, so the station got no alarm.
    core, siren = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    core.acknowledge(1, T0 + timedelta(minutes=1))
    core.handle(node_topic(1, "telemetry"), telemetry(1, 1, "NORMAL"), T0 + timedelta(minutes=2))

    core.handle(node_topic(2, "event"), event(2, 0, "ALERT", "FIRE"), T0 + timedelta(minutes=9))

    first, second = core.list_incidents()
    assert first.status == "ACKNOWLEDGED"
    assert second.status == "STATION_NOTIFIED" and second.first_node_id == 2
    assert siren.commands == [("on", 1), ("off", 1), ("on", 2)]


def test_acknowledge_silences_the_siren() -> None:
    core, siren = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    inc_id = core.list_incidents()[0].id

    inc = core.acknowledge(inc_id, T0 + timedelta(seconds=30))

    assert inc.status == "ACKNOWLEDGED" and inc.acknowledged_at == T0 + timedelta(seconds=30)
    assert siren.commands[-1] == ("off", inc_id)


def test_crew_status_must_follow_the_lifecycle() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    inc_id = core.list_incidents()[0].id

    core.acknowledge(inc_id, T0)
    core.assign(inc_id, crew_id=1, now=T0)

    with pytest.raises(ValueError, match="not allowed"):
        core.set_status(inc_id, "CLOSED", T0, crew_id=1)  # skips steps
    assert core.set_status(inc_id, "EN_ROUTE", T0, crew_id=1).status == "EN_ROUTE"


# --- crews -------------------------------------------------------------------------


def _acked_incident(core: Core, node_id: int = 1) -> int:
    core.handle(node_topic(node_id, "event"), event(node_id, 0, "ALERT", "FIRE"), T0)
    inc_id = core.list_incidents()[-1].id
    core.acknowledge(inc_id, T0)
    return inc_id


def test_a_crew_takes_an_acknowledged_incident() -> None:
    core, _ = make_core()
    inc_id = _acked_incident(core)

    inc = core.assign(inc_id, crew_id=2, now=T0)

    assert inc.assigned_crew == 2
    assert inc.events[-1].type == "crew_assigned" and inc.events[-1].payload == {"crew_id": 2}
    assert inc.to_json()["assigned_crew"] == 2


def test_an_incident_cannot_be_taken_twice_or_before_acknowledgement() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)
    with pytest.raises(ValueError, match="acknowledge"):
        core.assign(1, crew_id=1, now=T0)

    core.acknowledge(1, T0)
    core.assign(1, crew_id=1, now=T0)
    with pytest.raises(ValueError, match="already taken"):
        core.assign(1, crew_id=2, now=T0)


def test_only_the_assigned_crew_updates_the_status() -> None:
    core, _ = make_core()
    inc_id = _acked_incident(core)

    with pytest.raises(ValueError, match="take"):
        core.set_status(inc_id, "EN_ROUTE", T0, crew_id=1)  # nobody took it yet
    core.assign(inc_id, crew_id=1, now=T0)
    with pytest.raises(ValueError, match="crew 1"):
        core.set_status(inc_id, "EN_ROUTE", T0, crew_id=2)


def test_incident_json_lists_its_sensors() -> None:
    core, _ = make_core()
    inc_id = _acked_incident(core)

    assert core.list_incidents()[0].to_json()["node_ids"] == [1]
    assert inc_id == 1


# --- watchdog ------------------------------------------------------------------------


def test_silent_normal_node_goes_offline() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0), T0)

    assert core.watchdog(T0 + timedelta(seconds=39)) == []
    out = core.watchdog(T0 + timedelta(seconds=41))

    assert core.node(1).state == "OFFLINE"
    assert out[0]["kind"] == "node"


def test_silent_burning_node_is_lost_probably_burned_and_logged_on_its_incident() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)

    core.watchdog(T0 + timedelta(seconds=11))

    assert core.node(1).state == "LOST_PROBABLY_BURNED"
    assert core.list_incidents()[0].events[-1].type == "node_lost"


def test_after_a_rekindle_spread_goes_to_the_new_incident() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "event"), event(1, 0, "ALERT", "FIRE"), T0)  # incident 1
    core.acknowledge(1, T0)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 1, "NORMAL"), T0 + timedelta(minutes=1))
    core.handle(node_topic(1, "event"), event(1, 2, "ALERT", "FIRE"), T0 + timedelta(minutes=5))

    core.handle(node_topic(2, "event"), event(2, 0, "ALERT", "FIRE"), T0 + timedelta(minutes=6))

    old, new = core.list_incidents()
    assert new.node_ids == {1, 2} and new.events[-1].type == "fire_spread"
    assert 2 not in old.node_ids


def test_alarm_times_are_kept_per_node() -> None:
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT"), T0)
    core.handle(node_topic(1, "telemetry"), telemetry(1, 1, "FIRE"), T0 + timedelta(seconds=30))

    n = core.node(1).to_json()
    assert n["last_alert_at"] == "2026-07-20T14:00:00Z"
    assert n["last_fire_at"] == "2026-07-20T14:00:30Z"
    assert "vision" not in n and "vision_prob" not in n["readings"]  # ADR 0001: stays on the node


def test_a_message_carrying_the_camera_result_is_rejected() -> None:
    # The camera's result never leaves the node (ADR 0001); such a message breaks the contract.
    core, _ = make_core()
    core.handle(node_topic(1, "telemetry"), telemetry(1, 0, "ALERT", vision_prob=0.9), T0)

    assert core.stats(1)["rejected"] == 1 and core.node(1).state == "OFFLINE"


def test_restore_memory_after_a_restart() -> None:
    core, _ = make_core()
    core.restore_memory({1: {"ALERT": T0}})

    n = core.node(1).to_json()
    assert n["last_alert_at"] == "2026-07-20T14:00:00Z" and n["last_fire_at"] is None
