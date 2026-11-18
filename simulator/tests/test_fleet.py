from datetime import UTC, datetime, timedelta

from wamidh_sim.fleet import Fleet
from wamidh_sim.node import VirtualNode

CFG = {
    "intervals_s": {"NORMAL": 10, "ALERT": 5, "FIRE": 2},
    "ignite_ramp_s": 40,
    "camera": {"timezone": "Africa/Tunis", "daylight_local": ["06:30", "19:30"]},
}
T0 = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def entry(node_id: int) -> dict:  # type: ignore[type-arg]
    return {"node_id": node_id, "key_hex": f"{node_id:02x}" * 32, "control_port": 8100 + node_id}


def test_one_fleet_steps_every_powered_node_and_skips_unpowered_ones() -> None:
    fleet = Fleet([VirtualNode(entry(i), CFG) for i in (1, 2, 3)])
    fleet.nodes[1].powered = False

    topics = [topic for topic, _ in fleet.step(T0)]

    assert sorted({t.split("/")[3] for t in topics}) == ["1", "3"]


def test_fleet_reports_on_each_node_interval() -> None:
    fleet = Fleet([VirtualNode(entry(i), CFG) for i in (1, 2)])
    fleet.step(T0)

    assert fleet.step(T0 + timedelta(seconds=1)) == []  # NORMAL nodes wait 10 s
    assert len(fleet.step(T0 + timedelta(seconds=11))) == 2


def test_power_restored_reboots_the_node_calm() -> None:
    node = VirtualNode(entry(1), CFG)
    node.handle("POST", "/ignite", {"ramp": ["0"]})
    t = T0
    for _ in range(5):
        node.messages(t)
        t += timedelta(seconds=1)
    assert node.fw.state == "FIRE"

    node.handle("POST", "/power", {"on": ["0"]})  # burned
    node.handle("POST", "/extinguish", {})
    node.handle("POST", "/power", {"on": ["1"]})  # a new node, or the old one repaired

    assert node.fw.state == "NORMAL"
