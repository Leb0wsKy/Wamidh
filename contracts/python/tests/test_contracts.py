import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from wamidh_contracts import (
    NodeEvent,
    Telemetry,
    node_topic,
    parse_node_topic,
    sign,
    verify,
)

KEY = b"node-42-secret-key"
TELEMETRY = {
    "node_id": 42,
    "seq": 1024,
    "ts": "2026-10-01T12:00:00Z",
    "state": "ALERT",
    "gas_ratio": 0.62,
    "temp_c": 41.3,
    "rh_pct": 12.0,
    "flame": False,
    "fire_prob": 0.71,
    "battery_v": 3.28,
}
SCHEMA = Path(__file__).resolve().parents[2] / "telemetry.schema.json"


# --- signing ----------------------------------------------------------------------


def test_signed_message_verifies() -> None:
    msg = {**TELEMETRY, "sig": sign(TELEMETRY, KEY)}

    assert verify(msg, KEY)


def test_signature_does_not_depend_on_key_order() -> None:
    reordered = dict(reversed(list(TELEMETRY.items())))

    assert sign(reordered, KEY) == sign(TELEMETRY, KEY)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda m: m.update(state="NORMAL"),  # an attacker hides a fire
        lambda m: m.update(fire_prob=0.99),  # or injects one
        lambda m: m.pop("sig"),  # unsigned
        lambda m: m.update(sig="AAAA"),  # garbage signature
    ],
)
def test_tampered_or_unsigned_message_is_rejected(tamper) -> None:  # type: ignore[no-untyped-def]
    msg = {**TELEMETRY, "sig": sign(TELEMETRY, KEY)}
    tamper(msg)

    assert not verify(msg, KEY)


def test_wrong_key_is_rejected() -> None:
    msg = {**TELEMETRY, "sig": sign(TELEMETRY, KEY)}

    assert not verify(msg, b"another-node-key")


# --- models -----------------------------------------------------------------------


def test_telemetry_model_accepts_the_contract_example() -> None:
    t = Telemetry.model_validate({**TELEMETRY, "sig": "x"})

    assert t.node_id == 42 and t.state == "ALERT"


def test_telemetry_model_rejects_out_of_range_values() -> None:
    with pytest.raises(ValidationError):
        Telemetry.model_validate({**TELEMETRY, "fire_prob": 1.5, "sig": "x"})
    with pytest.raises(ValidationError):
        Telemetry.model_validate({**TELEMETRY, "state": "OFFLINE", "sig": "x"})  # backend-only


def test_telemetry_model_matches_the_json_schema_fields() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert set(Telemetry.model_fields) == set(schema["properties"])
    required = {name for name, f in Telemetry.model_fields.items() if f.is_required()}
    assert set(schema["required"]) == required


def test_the_camera_result_stays_on_the_node() -> None:
    # ADR 0001: the camera only feeds fire_prob on the node; nothing about it is transmitted.
    with pytest.raises(ValidationError):
        Telemetry.model_validate({**TELEMETRY, "vision_prob": 0.9, "sig": "x"})
    assert not {"vision_prob", "vision_night"} & set(Telemetry.model_fields)


def test_event_model() -> None:
    e = NodeEvent.model_validate(
        {"node_id": 3, "seq": 7, "ts": "2026-10-01T12:00:00Z", "from_state": "ALERT",
         "to_state": "FIRE", "fire_prob": 0.93, "flame": True, "sig": "x"}
    )

    assert e.to_state == "FIRE"


# --- topics -----------------------------------------------------------------------


def test_topics_round_trip() -> None:
    assert node_topic(42, "telemetry") == "wamidh/v1/nodes/42/telemetry"
    assert parse_node_topic("wamidh/v1/nodes/42/event") == (42, "event")
    assert parse_node_topic("wamidh/v1/stations/1/ack") is None
    assert parse_node_topic("wamidh/v1/nodes/x/event") is None
