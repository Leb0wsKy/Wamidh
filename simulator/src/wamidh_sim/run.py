"""Start every provisioned node (one fleet process) and the simulated world.

python -m wamidh_sim.run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from wamidh_sim.node import DEFAULT_CONFIG, load


def main() -> None:
    parser = argparse.ArgumentParser(description="Run all provisioned virtual nodes")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    _, registry = load(args.config)

    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "wamidh_sim.fleet", "--config", str(args.config)]
        )
    ]
    # The world: crews putting fires out clears the smoke around the nodes.
    procs.append(subprocess.Popen([sys.executable, "-m", "wamidh_sim.world"]))
    print(f"started {len(registry['nodes'])} nodes (Ctrl+C to stop)")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
