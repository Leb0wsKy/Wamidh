from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

from wamidh_backend.alerts import AlertsConfig, cap_xml, propose

CFG = AlertsConfig.from_dict(
    yaml.safe_load((Path(__file__).parents[1] / "config" / "alerts.yaml").read_text("utf-8"))
)
NOW = datetime(2026, 7, 20, 14, 5, tzinfo=UTC)
CAP = "{urn:oasis:names:tc:emergency:cap:1.2}"
INCIDENT = {"id": 7, "estimated_origin": {"lon": 8.70, "lat": 36.80}}


def square(lon: float, lat: float, d: float = 0.002) -> list[list[list[float]]]:
    return [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d],
             [lon - d, lat - d]]]  # fmt: skip


def near_zone(id_: int, name: str | None, near: str | None, people: int, km: float,
              towers: list[str], outline: dict | None = None) -> dict:  # type: ignore[type-arg]  # fmt: skip
    return {
        "id": id_,
        "name": name,
        "near": near,
        "population": people,
        "risk_level": "high",
        "distance_km": km,
        "tower_ids": towers,
        "outline": outline or {"type": "MultiPolygon", "coordinates": [square(8.7, 36.81)]},
    }


ZONES = [
    near_zone(2, "عين دراهم", "عين دراهم", 900, 1.24, ["605-2-1-1", "605-3-1-9"]),
    near_zone(5, None, "بلطة", 120, 2.5, ["605-2-1-1"]),
]


def test_proposal_people_towers_and_arabic_text() -> None:
    p = propose(INCIDENT, ZONES, CFG)

    assert p.people == 1020
    assert p.tower_ids == ["605-2-1-1", "605-3-1-9"]  # each tower once
    assert p.headline == "تحذير: حريق غابة قرب عين دراهم، دوار قرب بلطة"
    assert "1.2 كم" in p.description and "198" in p.instruction
    assert [z["label"] for z in p.zones] == ["عين دراهم", "دوار قرب بلطة"]


def test_proposal_names_at_most_three_zones() -> None:
    zones = [near_zone(i, f"قرية {i}", None, 10, i, []) for i in range(1, 6)]

    p = propose(INCIDENT, zones, CFG)

    assert p.headline.endswith("قرية 3 و2 مناطق أخرى")
    assert p.people == 50 and len(p.zones) == 5


def test_fire_at_the_village_uses_the_close_wording() -> None:
    p = propose(INCIDENT, [near_zone(1, None, None, 40, 0.1, [])], CFG)

    assert p.description.startswith("رُصد حريق غابة بجانب منطقة سكنية 1")


def test_no_zone_concerned_gives_an_empty_proposal() -> None:
    p = propose(INCIDENT, [], CFG)

    assert p.zones == [] and p.people == 0 and p.tower_ids == []


def test_cap_is_valid_cap_1_2_in_arabic() -> None:
    xml = cap_xml(propose(INCIDENT, ZONES, CFG), NOW, exercise=True, cfg=CFG)

    root = ET.fromstring(xml)
    assert root.tag == f"{CAP}alert"
    for tag in ("identifier", "sender", "sent", "status", "msgType", "scope"):
        assert root.findtext(f"{CAP}{tag}"), tag
    assert root.findtext(f"{CAP}status") == "Exercise"
    assert root.findtext(f"{CAP}sent") == "2026-07-20T14:05:00+00:00"
    info = root.find(f"{CAP}info")
    assert info is not None
    assert info.findtext(f"{CAP}language") == "ar-TN"
    assert info.findtext(f"{CAP}category") == "Fire"
    assert info.findtext(f"{CAP}expires") == "2026-07-20T16:05:00+00:00"
    assert info.findtext(f"{CAP}headline") == "تحذير: حريق غابة قرب عين دراهم، دوار قرب بلطة"
    params = {
        p.findtext(f"{CAP}valueName"): p.findtext(f"{CAP}value")
        for p in info.findall(f"{CAP}parameter")
    }
    assert params["cell_ids"] == "605-2-1-1 605-3-1-9"
    assert [a.findtext(f"{CAP}areaDesc") for a in info.findall(f"{CAP}area")] == [
        "عين دراهم",
        "دوار قرب بلطة",
    ]


def test_cap_actual_when_not_an_exercise() -> None:
    root = ET.fromstring(cap_xml(propose(INCIDENT, ZONES, CFG), NOW, exercise=False, cfg=CFG))

    assert root.findtext(f"{CAP}status") == "Actual"


def test_cap_polygons_lat_lon_closed() -> None:
    root = ET.fromstring(cap_xml(propose(INCIDENT, ZONES[:1], CFG), NOW, exercise=True, cfg=CFG))

    (polygon,) = root.iter(f"{CAP}polygon")
    pairs = (polygon.text or "").split(" ")
    assert pairs[0] == pairs[-1] and len(pairs) == 5
    lat, lon = (float(v) for v in pairs[0].split(","))
    assert (lat, lon) == (36.808, 8.698)  # latitude first, as CAP requires


def test_multipart_zone_in_cap() -> None:
    two_parts = {"type": "MultiPolygon", "coordinates": [square(8.70, 36.81), square(8.72, 36.81)]}
    zone = near_zone(3, "قرية", None, 50, 1.0, [], outline=two_parts)

    root = ET.fromstring(cap_xml(propose(INCIDENT, [zone], CFG), NOW, exercise=True, cfg=CFG))

    (area,) = root.iter(f"{CAP}area")
    assert len(area.findall(f"{CAP}polygon")) == 2


def test_cap_without_known_towers_targets_by_polygon_only() -> None:
    zones = [near_zone(2, "عين دراهم", None, 900, 1.2, [])]

    root = ET.fromstring(cap_xml(propose(INCIDENT, zones, CFG), NOW, exercise=True, cfg=CFG))

    info = root.find(f"{CAP}info")
    assert info is not None
    assert info.findall(f"{CAP}parameter") == []  # no empty cell list
    assert len(list(root.iter(f"{CAP}polygon"))) == 1  # the operator targets the outline
