"""What the node firmware does each sampling tick, without any I/O (testable).

Reports telemetry on the interval of its current state; on a state change it publishes an event
AND telemetry at once. Every message is sequenced and signed (contracts/mqtt_topics.md).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from wamidh_contracts import NodeReportedState, node_topic, sign

from wamidh_sim.camera import CameraModel, Vision
from wamidh_sim.classifier import NodeStateMachine, fire_probability
from wamidh_sim.sensors import SensorModel

Message = tuple[str, dict[str, Any]]


def iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


class NodeFirmware:
    def __init__(
        self,
        node_id: int,
        key: bytes,
        sensors: SensorModel,
        state_machine: NodeStateMachine,
        intervals_s: Mapping[str, float],
        camera: CameraModel | None = None,
    ) -> None:
        self.node_id = node_id
        self._key = key
        self._sensors = sensors
        self._sm = state_machine
        self._intervals = intervals_s
        self._camera = camera
        self.state: NodeReportedState = "NORMAL"
        self._seq = 0
        self._last_report: datetime | None = None

    def reboot(self) -> None:
        """Power came back: the classifier starts over in NORMAL. The sequence number survives
        (kept in flash), so the backend does not take the new messages for replays."""
        self._sm = type(self._sm)()
        self.state = "NORMAL"
        self._last_report = None

    def _signed(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {"node_id": self.node_id, "seq": self._seq, **payload}
        self._seq = (self._seq + 1) % 65536
        return {**payload, "sig": sign(payload, self._key)}

    def step(self, now: datetime, smoke: float) -> list[Message]:
        r = self._sensors.read(now, smoke)
        # Energy cascade (ADR 0001): the camera sleeps in NORMAL and wakes once the node is
        # already in ALERT or FIRE from an earlier reading. Its result only feeds fire_prob
        # here; it is never transmitted.
        vision: Vision | None = None
        if self._camera is not None and self.state in ("ALERT", "FIRE"):
            vision = self._camera.look(now, smoke, r.flame)
        prob = fire_probability(r, vision)
        new_state = self._sm.update(prob, r.flame)
        msgs: list[Message] = []

        changed = new_state != self.state
        if changed:
            msgs.append(
                (
                    node_topic(self.node_id, "event"),
                    self._signed(
                        {
                            "ts": iso(now),
                            "from_state": self.state,
                            "to_state": new_state,
                            "fire_prob": round(prob, 3),
                            "flame": r.flame,
                        }
                    ),
                )
            )
            self.state = new_state

        due = (
            self._last_report is None
            or (now - self._last_report).total_seconds() >= self._intervals[self.state]
        )
        if changed or due:
            msgs.append(
                (
                    node_topic(self.node_id, "telemetry"),
                    self._signed(
                        {
                            "ts": iso(now),
                            "state": self.state,
                            "gas_ratio": r.gas_ratio,
                            "temp_c": r.temp_c,
                            "rh_pct": r.rh_pct,
                            "flame": r.flame,
                            "fire_prob": round(prob, 3),
                            "battery_v": r.battery_v,
                        }
                    ),
                )
            )
            self._last_report = now
        return msgs
