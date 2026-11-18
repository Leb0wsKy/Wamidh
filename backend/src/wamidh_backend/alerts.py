"""Public alerts for the population (ADR 0003): which zones, how many people, which cell
towers, the Arabic text, and the CAP 1.2 message a Cell Broadcast Centre accepts.

Pure functions: nothing here sends anything. A dispatcher confirms every broadcast.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"
CLOSE_KM = 0.5  # nearer than this, the text says "next to" the zone instead of a distance


@dataclass(frozen=True)
class AlertsConfig:
    concern_radius_km: float
    cap: Mapping[str, Any]
    labels: Mapping[str, Any]
    headline: str
    description: str
    description_close: str
    instruction: str

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> AlertsConfig:
        return AlertsConfig(
            concern_radius_km=float(d["concern_radius_km"]),
            cap=d["cap"],
            labels=d["labels"],
            headline=d["headline"],
            description=d["description"],
            description_close=d["description_close"],
            instruction=d["instruction"],
        )


@dataclass(frozen=True)
class Proposal:
    incident_id: int
    zones: list[dict[str, Any]]  # each with "label", the Arabic name used in the text
    people: int
    tower_ids: list[str]
    headline: str
    description: str
    instruction: str
    radius_km: float = field(default=0.0)

    def to_json(self) -> dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "radius_km": self.radius_km,
            "zones": [{k: v for k, v in z.items() if k != "outline"} for z in self.zones],
            "people": self.people,
            "tower_ids": self.tower_ids,
            "headline": self.headline,
            "description": self.description,
            "instruction": self.instruction,
        }

    @property
    def message_ar(self) -> str:
        return f"{self.headline}\n{self.description}\n{self.instruction}"


def _label(zone: Mapping[str, Any], labels: Mapping[str, Any]) -> str:
    if zone.get("name"):
        return str(labels["named"]).format(name=zone["name"])
    if zone.get("near"):
        return str(labels["douar"]).format(near=zone["near"])
    return str(labels["unnamed"]).format(id=zone["id"])


def propose(
    incident: Mapping[str, Any], zones: list[dict[str, Any]], cfg: AlertsConfig
) -> Proposal:
    """The alert for `incident`, given the zones near its origin (nearest first)."""
    labelled = [{**z, "label": _label(z, cfg.labels)} for z in zones]
    towers = sorted({t for z in zones for t in z["tower_ids"]})
    names = [z["label"] for z in labelled]
    named = int(cfg.labels["max_named"])
    text = str(cfg.labels["separator"]).join(names[:named])
    if len(names) > named:
        text += " " + str(cfg.labels["more"]).format(n=len(names) - named)
    nearest = min((float(z["distance_km"]) for z in zones), default=0.0)
    template = cfg.description_close if nearest < CLOSE_KM else cfg.description
    return Proposal(
        incident_id=int(incident["id"]),
        zones=labelled,
        people=sum(int(z["population"]) for z in zones),
        tower_ids=towers,
        headline=cfg.headline.format(zones=text),
        description=template.format(zones=text, km=f"{nearest:.1f}"),
        instruction=cfg.instruction,
        radius_km=cfg.concern_radius_km,
    )


def _polygons(outline: Mapping[str, Any]) -> list[str]:
    """CAP polygons: one per outer ring, "lat,lon" pairs, first pair repeated at the end."""
    parts = (
        outline["coordinates"] if outline["type"] == "MultiPolygon" else [outline["coordinates"]]
    )
    out: list[str] = []
    for rings in parts:
        ring = [(round(lat, 5), round(lon, 5)) for lon, lat, *_ in rings[0]]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        out.append(" ".join(f"{lat},{lon}" for lat, lon in ring))
    return out


def cap_xml(proposal: Proposal, now: datetime, exercise: bool, cfg: AlertsConfig) -> str:
    """The CAP 1.2 alert. `exercise` marks a simulated broadcast (status "Exercise")."""
    cap = cfg.cap
    ET.register_namespace("", CAP_NS)

    def sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
        el = ET.SubElement(parent, f"{{{CAP_NS}}}{tag}")
        el.text = text
        return el

    root = ET.Element(f"{{{CAP_NS}}}alert")
    sub(root, "identifier", f"wamidh-{proposal.incident_id}-{int(now.timestamp())}")
    sub(root, "sender", str(cap["sender"]))
    sub(root, "sent", now.isoformat(timespec="seconds"))
    sub(root, "status", "Exercise" if exercise else "Actual")
    sub(root, "msgType", "Alert")
    sub(root, "scope", "Public")
    info = sub(root, "info")
    sub(info, "language", str(cap["language"]))
    sub(info, "category", str(cap["category"]))
    sub(info, "event", str(cap["event"]))
    for tag in ("urgency", "severity", "certainty"):
        sub(info, tag, str(cap[tag]))
    expires = now + timedelta(minutes=int(cap["expires_after_min"]))
    sub(info, "expires", expires.isoformat(timespec="seconds"))
    sub(info, "senderName", str(cap["sender_name"]))
    sub(info, "headline", proposal.headline)
    sub(info, "description", proposal.description)
    sub(info, "instruction", proposal.instruction)
    # Known towers are a hint for the operator. The <area> polygons are the targeting: the
    # operator picks its own cells covering them (OpenCelliD lists none in Kroumirie).
    if proposal.tower_ids:
        param = sub(info, "parameter")
        sub(param, "valueName", "cell_ids")
        sub(param, "value", " ".join(proposal.tower_ids))
    for zone in proposal.zones:
        area = sub(info, "area")
        sub(area, "areaDesc", zone["label"])
        for polygon in _polygons(zone["outline"]):
            sub(area, "polygon", polygon)
    return ET.tostring(root, encoding="unicode", xml_declaration=True)
