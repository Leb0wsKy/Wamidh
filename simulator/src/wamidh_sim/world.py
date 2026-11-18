"""The simulated world's response to the crews.

    python -m wamidh_sim.world     (started by wamidh_sim.run)

In the field, a crew putting a fire out is what clears the smoke; the sensors then return to
NORMAL on their own. Here the smoke lives in the virtual nodes, so this process plays that part:
when an incident is marked UNDER_CONTROL, CLOSED or FALSE_ALARM, it puts out the fire around the
incident's sensors (their control port). It never touches the backend's view of a node: the
node itself must sense clean air and report NORMAL, as a real one would.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from collections.abc import Iterable
from typing import Any

from wamidh_sim.ignite import call
from wamidh_sim.node import DEFAULT_CONFIG, load

log = logging.getLogger("world")
FIRE_OUT = {"UNDER_CONTROL", "CLOSED", "FALSE_ALARM"}


def fires_put_out(incidents: Iterable[dict[str, Any]], done: set[int]) -> list[int]:
    """Node ids whose fire the crews have now dealt with. `done` remembers incidents already
    handled, so a later rekindle (a new incident on the same sensor) is left burning."""
    nodes: list[int] = []
    for inc in incidents:
        if inc["status"] in FIRE_OUT and inc["id"] not in done:
            done.add(inc["id"])
            nodes.extend(inc.get("node_ids", []))
    return nodes


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg, registry = load(DEFAULT_CONFIG)
    ports = {n["node_id"]: n["control_port"] for n in registry["nodes"]}
    url = f"{cfg['backend_url']}/api/v1/incidents"
    done: set[int] | None = None
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3) as res:
                incidents = json.loads(res.read())
            if done is None:
                done = set()
                fires_put_out(incidents, done)  # incidents already over before we started
            for node_id in fires_put_out(incidents, done):
                if node_id in ports:
                    call(ports[node_id], "POST", "/extinguish")
                    log.warning("world: crew put out the fire at node %s", node_id)
        except OSError as e:
            log.info("world: backend not reachable yet (%s)", e)
        time.sleep(2)


if __name__ == "__main__":
    main()
