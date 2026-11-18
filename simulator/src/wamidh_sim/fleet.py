"""Every provisioned node in one process (the demo runs 200).

    python -m wamidh_sim.fleet      (started by wamidh_sim.run)

One process per node does not scale to a full installation: 200 Python interpreters take
gigabytes. Here the nodes share one event loop and one MQTT connection, the way a field gateway
forwards the packets of the nodes it serves. Each node still signs its own messages with its
own key and keeps its own control port, so `wamidh_sim.ignite` works unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiomqtt

from wamidh_sim.node import DEFAULT_CONFIG, VirtualNode, load

log = logging.getLogger("fleet")


class Fleet:
    def __init__(self, nodes: list[VirtualNode]) -> None:
        self.nodes = nodes

    def step(self, now: datetime) -> list[tuple[str, dict[str, Any]]]:
        """One sample of every node: all the messages due now."""
        return [m for node in self.nodes for m in node.messages(now)]

    async def publish_forever(self, mq: dict[str, Any], sample_s: float) -> None:
        while True:
            try:
                async with aiomqtt.Client(
                    mq["host"], mq["port"], identifier="wamidh-sim-fleet"
                ) as client:
                    log.info(
                        "fleet: %d nodes connected to %s:%s",
                        len(self.nodes),
                        mq["host"],
                        mq["port"],
                    )
                    while True:
                        for topic, payload in self.step(datetime.now(UTC)):
                            await client.publish(topic, json.dumps(payload), qos=1)
                        await asyncio.sleep(sample_s)
            except aiomqtt.MqttError as e:
                log.error("fleet: broker unreachable (%s), retrying in 3 s", e)
                await asyncio.sleep(3)

    async def run(self, cfg: dict[str, Any]) -> None:
        await asyncio.gather(
            *(node.serve_control() for node in self.nodes),
            self.publish_forever(cfg["mqtt"], cfg["sample_s"]),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run every provisioned virtual node")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    cfg, registry = load(args.config)
    fleet = Fleet([VirtualNode(entry, cfg) for entry in registry["nodes"]])
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None  # aiomqtt
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(fleet.run(cfg), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
