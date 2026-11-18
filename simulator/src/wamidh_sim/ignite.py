"""Act on the physical world around a node (what a lighter, a hose or a cut cable would do).

python -m wamidh_sim.ignite 12              # a fire starts next to node 12
python -m wamidh_sim.ignite 12 --ramp 10    # ... faster
python -m wamidh_sim.ignite 12 --out        # the fire is out
python -m wamidh_sim.ignite 12 --power off  # the node loses power
python -m wamidh_sim.ignite --list          # nodes and their state
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from wamidh_sim.node import DEFAULT_CONFIG, load


def call(port: int, method: str, path: str) -> dict[str, object]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method)
    with urllib.request.urlopen(req, timeout=3) as res:
        return json.loads(res.read())


def main() -> None:
    parser = argparse.ArgumentParser(description="Start or stop a fire next to a virtual node")
    parser.add_argument("node_id", type=int, nargs="?")
    parser.add_argument("--ramp", type=float, help="seconds for smoke to build up")
    parser.add_argument("--out", action="store_true", help="extinguish")
    parser.add_argument("--power", choices=["on", "off"])
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    _, registry = load(args.config)
    ports = {n["node_id"]: n["control_port"] for n in registry["nodes"]}

    if args.list or args.node_id is None:
        for nid, port in ports.items():
            try:
                print(call(port, "GET", "/status"))
            except OSError:
                print({"node_id": nid, "state": "process not running"})
        return
    if args.node_id not in ports:
        raise SystemExit(f"node {args.node_id} not provisioned; known: {sorted(ports)}")
    port = ports[args.node_id]
    if args.power:
        print(call(port, "POST", f"/power?on={1 if args.power == 'on' else 0}"))
    elif args.out:
        print(call(port, "POST", "/extinguish"))
    else:
        print(call(port, "POST", "/ignite" + (f"?ramp={args.ramp}" if args.ramp else "")))


if __name__ == "__main__":
    main()
