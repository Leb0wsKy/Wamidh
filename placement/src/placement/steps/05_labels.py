"""Step 05 — training labels.

Target years only (after fire_history.history_end_year; earlier years feed the history
features). Positive: a wildland cell containing the ignition proxy (first detection) of at
least one cleaned fire event in the target years. Negative: a wildland cell with no FIRMS
detection of any kind in the target years (so possibly burned cells are never labelled
"no fire"), sampled `negatives_per_positive` per positive with proportional allocation
across governorates (see placement.labels). Cells that burned only before the target years
may be negatives; excluding them would let the history features separate the classes by
construction.

Outputs (data/interim/): labels.parquet, labels.json (counts per governorate).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd

from placement.grid import Grid
from placement.history import HistoryWindows, in_window
from placement.io import step_main, write_json
from placement.labels import sample_negatives

log = logging.getLogger("placement.labels")


def _cell_ids(grid: Grid, df: pd.DataFrame) -> np.ndarray:
    rows, cols = grid.index(df.x.to_numpy(), df.y.to_numpy())
    ids = rows * grid.ncols + cols
    ids[rows < 0] = -1
    return ids


def run(cfg: dict[str, Any]) -> None:
    interim = cfg["paths"]["interim"]
    lc = cfg["labels"]
    grid = Grid(**json.loads((interim / "grid.json").read_text(encoding="utf-8")))
    cells = pd.read_parquet(interim / "cells.parquet")
    hc = cfg["fire_history"]
    w = HistoryWindows.from_years(hc["first_year"], hc["history_end_year"], hc["last_year"])
    # Labels come from the target years only; the years before feed the history features.
    ign = pd.read_parquet(interim / "fires_ignitions.parquet")
    ign = ign[in_window(ign, w.target_start, w.target_end)]
    every = pd.read_parquet(interim / "fires_all.parquet")
    every = every[in_window(every, w.target_start, w.target_end)]

    ign_ids = _cell_ids(grid, ign)
    positive = cells.cell_id.isin(ign_ids).to_numpy()
    burned = cells.cell_id.isin(_cell_ids(grid, every)).to_numpy()

    n_pos = int(positive.sum())
    n_neg = lc["negatives_per_positive"] * n_pos
    neg_idx = sample_negatives(cells, positive, burned, n_total=n_neg, seed=lc["seed"])

    labels = pd.concat(
        [
            cells.loc[positive, ["cell_id", "governorate"]].assign(label=1),
            cells.iloc[neg_idx][["cell_id", "governorate"]].assign(label=0),
        ],
        ignore_index=True,
    )
    labels.to_parquet(interim / "labels.parquet")

    in_wildland = int(np.isin(ign_ids, cells.cell_id).sum())
    summary = {
        "target_years": [w.target_start, w.target_end],
        "events": len(ign),
        "events_on_wildland_cells": in_wildland,
        "events_elsewhere": len(ign) - in_wildland,
        "positive_cells": n_pos,
        "negative_cells": int(len(neg_idx)),
        "cells_excluded_any_detection": int((burned & ~positive).sum()),
        "wildland_cells": len(cells),
        "by_governorate": {
            str(g): {"pos": int((grp.label == 1).sum()), "neg": int((grp.label == 0).sum())}
            for g, grp in labels.groupby("governorate")
        },
    }
    write_json(interim / "labels.json", summary)
    log.info("labels: %s", json.dumps(summary, indent=1))


if __name__ == "__main__":
    step_main(run, "Step 05 - training labels")
