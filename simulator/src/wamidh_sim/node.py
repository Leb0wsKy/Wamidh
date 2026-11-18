"""One virtual node as its own process.

    python -m wamidh_sim.node --id 12

Publishes signed telemetry/events over MQTT like the firmware will, and opens a local control
port (127.0.0.1 only) standing in for the physical world:
  GET  /status                 current state and smoke level
  POST /ignite?ramp=40         a fire starts next to the node
  POST /extinguish             the fire is out
  POST /power?on=0|1           cut or restore power (to test offline detection)
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
from urllib.parse import parse_qs, urlsplit

import aiomqtt
import yaml

from wamidh_sim.camera import camera_from_config
from wamidh_sim.classifier import NodeStateMachine
from wamidh_sim.environment import SmokeEnvironment
from wamidh_sim.firmware import NodeFirmware
from wamidh_sim.sensors import SensorModel

REPO = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO / "simulator" / "config" / "demo.yaml"
log = logging.getLogger("node")


def load(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    registry_path = REPO / cfg["registry"]
    if not registry_path.exists():
        raise SystemExit(f"{registry_path} missing: run `python -m wamidh_sim.provision`")
    return cfg, json.loads(registry_path.read_text(encoding="utf-8"))


class VirtualNode:
    def __init__(self, entry: dict[str, Any], cfg: dict[str, Any]) -> None:
        self.entry = entry
        self.cfg = cfg
        self.env = SmokeEnvironment()
        self.powered = True
        self.fw = NodeFirmware(
            node_id=entry["node_id"],
            key=bytes.fromhex(entry["key_hex"]),
            sensors=SensorModel(seed=entry["node_id"]),
            state_machine=NodeStateMachine(),
            intervals_s=cfg["intervals_s"],
            camera=camera_from_config(cfg["camera"], seed=entry["node_id"]),
        )

    # --- physical world (control port) ------------------------------------------------

    def handle(self, method: str, path: str, query: dict[str, list[str]]) -> dict[str, Any]:
        now = datetime.now(UTC)
        if method == "POST" and path == "/ignite":
            ramp = float(query.get("ramp", [self.cfg["ignite_ramp_s"]])[0])
            self.env.set_target(1.0, ramp, now)
            log.warning("node %s: fire started nearby (smoke ramp %.0f s)", self.fw.node_id, ramp)
        elif method == "POST" and path == "/extinguish":
            self.env.set_target(0.0, 0, now)
            log.warning("node %s: fire out", self.fw.node_id)
        elif method == "POST" and path == "/power":
            was_on = self.powered
            self.powered = query.get("on", ["1"])[0] not in ("0", "false", "off")
            if self.powered and not was_on:
                self.fw.reboot()
            log.warning("node %s: power %s", self.fw.node_id, "on" if self.powered else "OFF")
        elif not (method == "GET" and path == "/status"):
            return {"error": f"unknown {method} {path}"}
        return {
            "node_id": self.fw.node_id,
            "state": self.fw.state,
            "smoke": round(self.env.level(now), 2),
            "powered": self.powered,
        }

    async def serve_control(self) -> None:
        async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                request_line = (await reader.readline()).decode().split()
                while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                    pass  # headers are not needed
                method, target = request_line[0], request_line[1]
                url = urlsplit(target)
                body = json.dumps(self.handle(method, url.path, parse_qs(url.query))).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
            except (IndexError, ConnectionError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(on_client, "127.0.0.1", self.entry["control_port"])
        async with server:
            await server.serve_forever()

    # --- radio link -------------------------------------------------------------------

    def messages(self, now: datetime) -> list[tuple[str, dict[str, Any]]]:
        """One sensor sample: the signed messages due now (none while the power is cut)."""
        if not self.powered:
            return []
        out = self.fw.step(now, self.env.level(now))
        for topic, payload in out:
            if topic.endswith("/event"):
                log.warning(
                    "node %s: %s -> %s (p=%.2f)",
                    self.fw.node_id,
                    payload["from_state"],
                    payload["to_state"],
                    payload["fire_prob"],
                )
        return out

    async def publish_forever(self) -> None:
        mq = self.cfg["mqtt"]
        while True:
            try:
                async with aiomqtt.Client(
                    mq["host"], mq["port"], identifier=f"wamidh-node-{self.fw.node_id}"
                ) as client:
                    log.info("node %s: connected to %s:%s", self.fw.node_id, mq["host"], mq["port"])
                    while True:
                        for topic, payload in self.messages(datetime.now(UTC)):
                            await client.publish(topic, json.dumps(payload), qos=1)
                        await asyncio.sleep(self.cfg["sample_s"])
            except aiomqtt.MqttError as e:
                log.error("node %s: broker unreachable (%s), retrying in 3 s", self.fw.node_id, e)
                await asyncio.sleep(3)

    async def run(self) -> None:
        await asyncio.gather(self.serve_control(), self.publish_forever())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one virtual Wamidh node")
    parser.add_argument("--id", type=int, required=True, help="node_id from the registry")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    cfg, registry = load(args.config)
    entry = next((n for n in registry["nodes"] if n["node_id"] == args.id), None)
    if entry is None:
        raise SystemExit(f"node {args.id} is not in the registry")
    node = VirtualNode(entry, cfg)
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None  # aiomqtt
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(node.run(), loop_factory=loop_factory)


if __name__ == "__main__":
    main()
