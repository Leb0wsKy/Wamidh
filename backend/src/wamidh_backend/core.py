"""Backend domain logic without I/O: ingest, node state, incidents, watchdog (CLAUDE.md s. 8).

Every public method returns the live events to push to dashboards
(`{"kind": "node", ...}` / `{"kind": "incident", ...}`, contracts/api.md).
"""

from __future__ import annotations

import json
import logging
import math
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError
from wamidh_contracts import NodeEvent, NodeState, Telemetry, parse_node_topic, verify

log = logging.getLogger("wamidh.core")
LiveEvent = dict[str, Any]
Siren = Callable[[str, int], None]  # ("on" | "off", incident_id)

CREW_NEXT: dict[str, tuple[str, ...]] = {
    "ACKNOWLEDGED": ("EN_ROUTE", "FALSE_ALARM"),
    "EN_ROUTE": ("ON_SITE", "FALSE_ALARM"),
    "ON_SITE": ("UNDER_CONTROL", "FALSE_ALARM"),
    "UNDER_CONTROL": ("CLOSED",),
}
CLOSED = {"CLOSED", "FALSE_ALARM"}


def iso(ts: datetime | None) -> str | None:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def km_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    (lon1, lat1), (lon2, lat2) = a, b
    r = math.pi / 180
    h = (
        math.sin((lat2 - lat1) * r / 2) ** 2
        + math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


@dataclass
class NodeInfo:
    """What installation registers about a node."""

    node_id: int
    key: bytes
    lon: float
    lat: float
    risk_percentile: float | None
    gateway_id: int | None
    access: dict[str, Any] | None


@dataclass
class NodeView:
    info: NodeInfo
    state: NodeState = "OFFLINE"
    last_seen: datetime | None = None
    battery_v: float | None = None
    readings: dict[str, Any] = field(default_factory=dict)
    last_alert_at: datetime | None = None
    last_fire_at: datetime | None = None

    def to_json(self) -> dict[str, Any]:
        i = self.info
        return {
            "id": i.node_id,
            "lon": i.lon,
            "lat": i.lat,
            "state": self.state,
            "last_seen": iso(self.last_seen),
            "battery_v": self.battery_v,
            "risk_percentile": i.risk_percentile,
            "gateway_id": i.gateway_id,
            "readings": self.readings,
            "access_point": i.access,
            "last_alert_at": iso(self.last_alert_at),
            "last_fire_at": iso(self.last_fire_at),
        }


@dataclass
class IncidentEvent:
    ts: datetime
    type: str
    payload: dict[str, Any]


@dataclass
class Incident:
    id: int
    status: str
    first_node_id: int
    estimated_origin: dict[str, float]
    created_at: datetime
    access_point: dict[str, Any] | None
    acknowledged_at: datetime | None = None
    events: list[IncidentEvent] = field(default_factory=list)
    node_ids: set[int] = field(default_factory=set)
    assigned_crew: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "first_node_id": self.first_node_id,
            "estimated_origin": self.estimated_origin,
            "created_at": iso(self.created_at),
            "acknowledged_at": iso(self.acknowledged_at),
            "access_point": self.access_point,
            "node_ids": sorted(self.node_ids),
            "assigned_crew": self.assigned_crew,
            "events": [
                {"ts": iso(e.ts), "type": e.type, "payload": e.payload} for e in self.events
            ],
        }


@dataclass
class _LinkStats:
    received: int = 0
    lost: int = 0
    rejected: int = 0
    last_seq: int | None = None
    seen: deque[int] = field(default_factory=lambda: deque(maxlen=256))


class Core:
    def __init__(
        self,
        nodes: list[NodeInfo],
        silent_after_s: Mapping[str, float],
        siren: Siren,
        join_radius_km: float = 3.0,
        join_window: timedelta = timedelta(minutes=60),
    ) -> None:
        self._nodes = {n.node_id: NodeView(n) for n in nodes}
        self._stats = {n.node_id: _LinkStats() for n in nodes}
        self._silent = silent_after_s
        self._siren = siren
        self._join_km = join_radius_km
        self._join_window = join_window
        self._incidents: dict[int, Incident] = {}
        self._next_id = 1

    def attach_siren(self, siren: Siren) -> None:
        """Route siren commands to the station (MQTT in production)."""
        self._siren = siren

    def restore(self, incidents: list[Incident]) -> None:
        """Reload incidents saved before a restart."""
        self._incidents = {i.id: i for i in incidents}
        self._next_id = max(self._incidents, default=0) + 1

    # --- queries ---------------------------------------------------------------------

    def node(self, node_id: int) -> NodeView:
        return self._nodes[node_id]

    def restore_memory(self, memory: Mapping[int, Mapping[str, Any]]) -> None:
        """Last alert / fire times, from the store at startup."""
        for node_id, m in memory.items():
            node = self._nodes.get(node_id)
            if node is None:
                continue  # a node no longer installed
            node.last_alert_at = m.get("ALERT")
            node.last_fire_at = m.get("FIRE")

    @property
    def silent_after_s(self) -> Mapping[str, float]:
        """Silence (s) after which the watchdog acts, per state."""
        return self._silent

    def list_nodes(self) -> list[NodeView]:
        return list(self._nodes.values())

    def list_incidents(self) -> list[Incident]:
        return list(self._incidents.values())

    def stats(self, node_id: int) -> dict[str, int]:
        s = self._stats[node_id]
        return {"received": s.received, "lost": s.lost, "rejected": s.rejected}

    # --- ingest ----------------------------------------------------------------------

    def handle(self, topic: str, raw: bytes, now: datetime) -> list[LiveEvent]:
        parsed = parse_node_topic(topic)
        if parsed is None or parsed[0] not in self._nodes:
            return []
        node_id, kind = parsed
        msg = self._authentic(node_id, raw)
        if msg is None:
            self._stats[node_id].rejected += 1
            log.warning("rejected message on %s", topic)
            return []
        try:
            model: Telemetry | NodeEvent = (
                Telemetry.model_validate(msg)
                if kind == "telemetry"
                else NodeEvent.model_validate(msg)
            )
        except ValidationError:
            self._stats[node_id].rejected += 1
            log.warning("invalid payload on %s", topic)
            return []
        if not self._count(node_id, model.seq):
            return []  # duplicate (QoS 1 redelivery)

        node = self._nodes[node_id]
        was = node.state
        node.last_seen = now
        if isinstance(model, Telemetry):
            node.state = model.state
            node.battery_v = model.battery_v
            node.readings = {
                "gas_ratio": model.gas_ratio,
                "temp_c": model.temp_c,
                "rh_pct": model.rh_pct,
                "flame": model.flame,
                "fire_prob": model.fire_prob,
            }
        else:
            node.state = model.to_state
        if node.state == "ALERT":
            node.last_alert_at = now
        elif node.state == "FIRE":
            node.last_fire_at = now

        out: list[LiveEvent] = [{"kind": "node", "node": node.to_json()}]
        if node.state == "FIRE" and was != "FIRE":
            out += self._on_fire(node, now)
        return out

    def _authentic(self, node_id: int, raw: bytes) -> dict[str, Any] | None:
        try:
            msg = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(msg, dict) or msg.get("node_id") != node_id:
            return None
        return msg if verify(msg, self._nodes[node_id].info.key) else None

    def _count(self, node_id: int, seq: int) -> bool:
        s = self._stats[node_id]
        if seq in s.seen:
            return False
        s.seen.append(seq)
        s.received += 1
        if s.last_seq is not None:
            delta = (seq - s.last_seq) % 65536
            if 0 < delta < 32768:
                s.lost += delta - 1
                s.last_seq = seq
            elif s.lost:
                s.lost -= 1  # a late packet we had counted as lost
        else:
            s.last_seq = seq
        return True

    # --- incidents -------------------------------------------------------------------

    def _on_fire(self, node: NodeView, now: datetime) -> list[LiveEvent]:
        here = (node.info.lon, node.info.lat)
        # Newest first: after a rekindle, the same sensor belongs to an old (extinguished) and a
        # new incident; a spread belongs to the fire burning now.
        for inc in sorted(self._incidents.values(), key=lambda i: i.id, reverse=True):
            if inc.status in CLOSED or now - inc.created_at > self._join_window:
                continue
            # Only a fire that is still burning can spread: at least one of the incident's
            # other sensors must still be in FIRE (or lost in it). If they have all returned to
            # NORMAL, this is a new fire (or a rekindle) and must alarm the station again.
            others = [n for n in inc.node_ids if n != node.info.node_id]
            burning = any(self._nodes[n].state in ("FIRE", "LOST_PROBABLY_BURNED") for n in others)
            near = any(
                km_between(here, (self._nodes[n].info.lon, self._nodes[n].info.lat))
                <= self._join_km
                for n in others
            )
            if burning and near:
                inc.node_ids.add(node.info.node_id)
                inc.events.append(IncidentEvent(now, "fire_spread", {"node_id": node.info.node_id}))
                log.warning("incident %s: fire spread to node %s", inc.id, node.info.node_id)
                return [{"kind": "incident", "incident": inc.to_json()}]

        inc = Incident(
            id=self._next_id,
            status="NEW",
            first_node_id=node.info.node_id,
            estimated_origin={"lon": node.info.lon, "lat": node.info.lat},
            created_at=now,
            access_point=node.info.access,
            node_ids={node.info.node_id},
        )
        self._next_id += 1
        inc.events.append(IncidentEvent(now, "node_fire", {"node_id": node.info.node_id}))
        self._incidents[inc.id] = inc
        self._siren("on", inc.id)
        inc.status = "STATION_NOTIFIED"
        inc.events.append(IncidentEvent(now, "station_notified", {}))
        log.warning("incident %s opened by node %s", inc.id, node.info.node_id)
        return [{"kind": "incident", "incident": inc.to_json()}]

    def acknowledge(self, incident_id: int, now: datetime) -> Incident:
        inc = self._incidents[incident_id]
        if inc.status not in ("NEW", "STATION_NOTIFIED"):
            raise ValueError(f"incident {incident_id} is already {inc.status}")
        inc.status = "ACKNOWLEDGED"
        inc.acknowledged_at = now
        inc.events.append(IncidentEvent(now, "acknowledged", {}))
        self._siren("off", inc.id)
        return inc

    def assign(self, incident_id: int, crew_id: int, now: datetime) -> Incident:
        """A crew takes the incident. One crew per incident; the station acknowledges first."""
        inc = self._incidents[incident_id]
        if inc.status in CLOSED:
            raise ValueError(f"incident {incident_id} is {inc.status}")
        if inc.status in ("NEW", "STATION_NOTIFIED"):
            raise ValueError(f"the station must acknowledge incident {incident_id} first")
        if inc.assigned_crew is not None and inc.assigned_crew != crew_id:
            raise ValueError(f"incident {incident_id} already taken by crew {inc.assigned_crew}")
        if inc.assigned_crew != crew_id:
            inc.assigned_crew = crew_id
            inc.events.append(IncidentEvent(now, "crew_assigned", {"crew_id": crew_id}))
        return inc

    def set_status(
        self, incident_id: int, status: str, now: datetime, crew_id: int | None = None
    ) -> Incident:
        inc = self._incidents[incident_id]
        if inc.assigned_crew is None:
            raise ValueError(f"a crew must take incident {incident_id} first")
        if crew_id != inc.assigned_crew:
            raise ValueError(f"incident {incident_id} is handled by crew {inc.assigned_crew}")
        if status not in CREW_NEXT.get(inc.status, ()):
            raise ValueError(f"transition {inc.status} -> {status} not allowed")
        inc.status = status
        inc.events.append(IncidentEvent(now, "status", {"status": status}))
        return inc

    def record(self, incident_id: int, kind: str, payload: dict[str, Any], now: datetime) -> None:
        """Append an event to the incident's audit log (actions taken outside the core)."""
        self._incidents[incident_id].events.append(IncidentEvent(now, kind, payload))

    # --- watchdog --------------------------------------------------------------------

    def watchdog(self, now: datetime) -> list[LiveEvent]:
        out: list[LiveEvent] = []
        for node in self._nodes.values():
            if node.last_seen is None or node.state in ("OFFLINE", "LOST_PROBABLY_BURNED"):
                continue
            if (now - node.last_seen).total_seconds() <= self._silent[node.state]:
                continue
            burning = node.state == "FIRE"
            node.state = "LOST_PROBABLY_BURNED" if burning else "OFFLINE"
            out.append({"kind": "node", "node": node.to_json()})
            log.warning("node %s silent -> %s", node.info.node_id, node.state)
            if burning:
                for inc in self._incidents.values():
                    if node.info.node_id in inc.node_ids and inc.status not in CLOSED:
                        inc.events.append(
                            IncidentEvent(now, "node_lost", {"node_id": node.info.node_id})
                        )
                        out.append({"kind": "incident", "incident": inc.to_json()})
        return out
