"""MQTT topic names (contracts/mqtt_topics.md)."""

from __future__ import annotations

import re
from typing import Literal

PREFIX = "wamidh/v1"
NodeTopicKind = Literal["telemetry", "event"]

NODE_WILDCARD = f"{PREFIX}/nodes/+/+"
STATION_ACK_WILDCARD = f"{PREFIX}/stations/+/ack"
_NODE_RE = re.compile(rf"^{re.escape(PREFIX)}/nodes/(\d+)/(telemetry|event)$")


def node_topic(node_id: int, kind: NodeTopicKind) -> str:
    return f"{PREFIX}/nodes/{node_id}/{kind}"


def station_cmd_topic(station_id: int) -> str:
    return f"{PREFIX}/stations/{station_id}/cmd"


def parse_node_topic(topic: str) -> tuple[int, NodeTopicKind] | None:
    m = _NODE_RE.match(topic)
    if not m:
        return None
    kind: NodeTopicKind = "telemetry" if m.group(2) == "telemetry" else "event"
    return int(m.group(1)), kind
