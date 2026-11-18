"""Fire-history features and the time windows that keep them honest.

Training: history features from [train_start, train_end], labels from the years after.
Deployment: history features from the most recent window of the *same length*, so counts
and distances have the same scale the model was trained on.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import shapely

from placement.features import count_within, distance_to_points


@dataclass(frozen=True)
class HistoryWindows:
    train_start: int
    train_end: int
    target_start: int
    target_end: int
    deploy_start: int
    deploy_end: int

    @classmethod
    def from_years(cls, first_year: int, history_end_year: int, last_year: int) -> HistoryWindows:
        length = history_end_year - first_year + 1
        return cls(
            train_start=first_year,
            train_end=history_end_year,
            target_start=history_end_year + 1,
            target_end=last_year,
            deploy_start=last_year - length + 1,
            deploy_end=last_year,
        )


def in_window(df: pd.DataFrame, start: int, end: int) -> pd.Series:
    year = df["time"].dt.year
    return (year >= start) & (year <= end)


def history_features(
    cells: pd.DataFrame, ignitions: pd.DataFrame, detections: pd.DataFrame, radii_m: list[int]
) -> pd.DataFrame:
    """Per cell: past fire starts within each radius, past detections within 1 km, and the
    distance to the nearest past fire start. Inputs must already be restricted to one window."""
    x, y = cells.x.to_numpy(), cells.y.to_numpy()
    ix, iy = ignitions.x.to_numpy(), ignitions.y.to_numpy()
    out = pd.DataFrame({"cell_id": cells.cell_id.to_numpy()})
    for r in radii_m:
        out[f"hist_ign_{r // 1000}km"] = count_within(x, y, ix, iy, r)
    out["hist_det_1km"] = count_within(x, y, detections.x.to_numpy(), detections.y.to_numpy(), 1000)
    out["dist_hist_ign_m"] = distance_to_points(x, y, list(shapely.points(ix, iy)))
    return out


def rank_normalise(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Replace each column by its rank within this table, scaled to [0, 1] (ties averaged).

    Recent windows contain more detections (VIIRS from 2012 sees smaller fires, and fire
    activity changed), so raw counts are not comparable between the training and the
    deployment window. Ranks keep the ordering the model uses and remove the level shift.
    """
    out = df.copy()
    n = len(df)
    for c in cols:
        out[c] = (df[c].rank(method="average") - 1) / max(n - 1, 1)
    return out
