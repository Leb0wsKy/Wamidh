from datetime import UTC, datetime, timedelta

import pytest
from wamidh_contracts import parse_node_topic, verify

from wamidh_sim.classifier import NodeStateMachine, fire_probability
from wamidh_sim.firmware import NodeFirmware
from wamidh_sim.sensors import Readings, SensorModel

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)  # summer afternoon
KEY = b"k" * 32


# --- sensors -------------------------------------------------------------------------


def test_clean_air_reads_near_baseline() -> None:
    r = SensorModel(seed=1).read(T0, smoke=0.0)

    assert 0.9 < r.gas_ratio < 1.1
    assert not r.flame
    assert 3.3 <= r.battery_v <= 4.2


def test_heavy_smoke_drops_gas_ratio_heats_and_shows_flame() -> None:
    clean = SensorModel(seed=1).read(T0, smoke=0.0)
    smoky = SensorModel(seed=1).read(T0, smoke=1.0)

    assert smoky.gas_ratio < 0.5
    assert smoky.temp_c > clean.temp_c + 20
    assert smoky.flame


# --- classifier ----------------------------------------------------------------------


def test_normal_summer_afternoon_is_not_a_fire() -> None:
    assert fire_probability(Readings(1.0, 38.0, 25.0, False, 4.0)) < 0.1


def test_fog_never_reaches_fire() -> None:
    # High humidity and a gas dip, cool, no flame (CLAUDE.md false_alarm_fog scenario).
    assert fire_probability(Readings(0.75, 17.0, 98.0, False, 3.9)) < 0.4


def test_growing_smoke_goes_alert_then_fire() -> None:
    model = SensorModel(seed=2)
    probs = [fire_probability(model.read(T0, s)) for s in (0.0, 0.4, 0.7)]

    assert probs[0] < 0.4 <= probs[1] < 0.8 <= probs[2]


def test_state_machine_escalates_at_once_and_calms_down_slowly() -> None:
    sm = NodeStateMachine(alert=0.4, fire=0.8, clear_readings=3)

    assert sm.update(0.5, flame=False) == "ALERT"
    assert sm.update(0.95, flame=False) == "FIRE"
    assert [sm.update(0.1, flame=False) for _ in range(3)] == ["FIRE", "FIRE", "NORMAL"]


def test_flame_alone_confirms_fire() -> None:
    assert NodeStateMachine().update(0.2, flame=True) == "FIRE"


# --- firmware ------------------------------------------------------------------------


def _firmware() -> NodeFirmware:
    return NodeFirmware(
        node_id=7,
        key=KEY,
        sensors=SensorModel(seed=3),
        state_machine=NodeStateMachine(),
        intervals_s={"NORMAL": 10, "ALERT": 5, "FIRE": 2},
    )


def test_reports_on_the_state_interval_only() -> None:
    fw = _firmware()

    first = fw.step(T0, smoke=0.0)
    quiet = fw.step(T0 + timedelta(seconds=4), smoke=0.0)
    due = fw.step(T0 + timedelta(seconds=10), smoke=0.0)

    assert [parse_node_topic(t) for t, _ in first] == [(7, "telemetry")]
    assert quiet == []
    assert len(due) == 1


def test_state_change_is_published_immediately_with_an_event() -> None:
    fw = _firmware()
    fw.step(T0, smoke=0.0)

    msgs = fw.step(T0 + timedelta(seconds=1), smoke=1.0)

    kinds = [parse_node_topic(t)[1] for t, _ in msgs]  # type: ignore[index]
    assert kinds == ["event", "telemetry"]
    event = msgs[0][1]
    assert (event["from_state"], event["to_state"]) == ("NORMAL", "FIRE")


def test_every_message_is_signed_and_sequenced() -> None:
    fw = _firmware()
    msgs = fw.step(T0, smoke=0.0) + fw.step(T0 + timedelta(seconds=1), smoke=1.0)

    assert all(verify(p, KEY) for _, p in msgs)
    assert [p["seq"] for _, p in msgs] == [0, 1, 2]


@pytest.mark.parametrize("state", ["NORMAL", "ALERT", "FIRE"])
def test_payload_matches_the_contract(state: str) -> None:
    from wamidh_contracts import Telemetry

    fw = _firmware()
    smoke = {"NORMAL": 0.0, "ALERT": 0.4, "FIRE": 1.0}[state]
    (_, payload), *_ = [m for m in fw.step(T0, smoke) if parse_node_topic(m[0])[1] == "telemetry"]  # type: ignore[index]

    Telemetry.model_validate(payload)  # raises if the node drifts from the contract


def test_the_camera_wakes_once_alarmed_feeds_fire_prob_and_is_never_transmitted() -> None:
    from datetime import time
    from zoneinfo import ZoneInfo

    from wamidh_sim.camera import CameraModel

    def firmware(with_camera: bool) -> NodeFirmware:
        camera = CameraModel(
            seed=3, daylight=(time(6, 30), time(19, 30)), tz=ZoneInfo("Africa/Tunis")
        )
        return NodeFirmware(
            node_id=7,
            key=KEY,
            sensors=SensorModel(seed=3),
            state_machine=NodeStateMachine(),
            intervals_s={"NORMAL": 10, "ALERT": 5, "FIRE": 2},
            camera=camera if with_camera else None,
        )

    def tele(msgs: list) -> dict:  # type: ignore[type-arg]
        return [p for t, p in msgs if parse_node_topic(t)[1] == "telemetry"][0]  # type: ignore[index]

    # Same smoke, same sensor noise: once the node is alarmed, the awake camera (daytime in
    # Tunis at 14:00 UTC) sees the smoke and raises the node's own fire probability.
    probs = {}
    for with_camera in (False, True):
        fw = firmware(with_camera)
        fw.step(T0, smoke=0.45)  # enters ALERT; the camera was asleep
        msg = tele(fw.step(T0 + timedelta(seconds=5), smoke=0.45))  # camera awake now
        assert not {"vision_prob", "vision_night"} & set(msg)  # ADR 0001: stays on the node
        assert verify(msg, KEY)
        probs[with_camera] = msg["fire_prob"]
    assert probs[True] > probs[False]
