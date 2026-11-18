"""Run the placement pipeline end to end.

    python -m placement.pipeline --config config/pilot_kroumirie.yaml [--from 03] [--to 05]

Step 01 (downloads, Earth Engine exports) is run separately; see data/README.md.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import time

from placement.config import load_config

STEPS = [
    "02_clean_fires",
    "03_grid",
    "04_features",
    "05_labels",
    "06_train",
    "07_predict",
    "08_optimise",
    "09_figures",
]

log = logging.getLogger("placement.pipeline")


def main() -> None:
    parser = argparse.ArgumentParser(description="Wamidh placement pipeline")
    parser.add_argument("--config", required=True)
    parser.add_argument("--from", dest="start", default=STEPS[0][:2], help="first step, e.g. 03")
    parser.add_argument("--to", dest="end", default=STEPS[-1][:2], help="last step, e.g. 05")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    for name in STEPS:
        if not args.start <= name[:2] <= args.end:
            continue
        t0 = time.perf_counter()
        log.info("=== step %s ===", name)
        importlib.import_module(f"placement.steps.{name}").run(cfg)
        log.info("step %s done in %.1f s", name, time.perf_counter() - t0)


if __name__ == "__main__":
    main()
