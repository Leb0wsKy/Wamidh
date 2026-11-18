"""Cleaning of FIRMS active-fire detections (CLAUDE.md §6.2 step 2)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

COLUMNS = ["source", "lat", "lon", "time", "confidence", "frp", "daynight", "type"]


def normalise(raw: pd.DataFrame, source: str) -> pd.DataFrame:
    """Common schema for VIIRS and MODIS rows. `time` is UTC from acq_date + acq_time (HHMM)."""
    hhmm = raw["acq_time"].astype(int).astype(str).str.zfill(4)
    time = pd.to_datetime(raw["acq_date"] + " " + hhmm, format="%Y-%m-%d %H%M", utc=True)
    return pd.DataFrame(
        {
            "source": source,
            "lat": raw["latitude"].astype(float),
            "lon": raw["longitude"].astype(float),
            "time": time,
            "confidence": raw["confidence"].astype(str),  # VIIRS l/n/h, MODIS 0-100
            "frp": raw["frp"].astype(float),
            "daynight": raw["daynight"],
            "type": raw["type"].astype(int) if "type" in raw else 0,
        },
        columns=COLUMNS,
    )


def filter_detections(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    """Fire-season, confident, non-negligible, presumed-vegetation detections.

    FIRMS `type`: 0 presumed vegetation fire, 1 volcano, 2 other static land source
    (e.g. gas flares, industry), 3 offshore. Only 0 is kept.
    """
    in_season = df["time"].dt.month.isin(cfg["season_months"])
    is_viirs = df["source"] == "VIIRS"
    conf_ok = np.where(
        is_viirs,
        df["confidence"].astype(str).isin(cfg["viirs_min_confidence"]),
        pd.to_numeric(df["confidence"], errors="coerce") >= cfg["modis_min_confidence"],
    )
    keep = in_season & conf_ok & (df["frp"] >= cfg["min_frp_mw"]) & (df["type"] == 0)
    return df[keep].reset_index(drop=True)


def cluster_events(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    t_days: NDArray[np.float64],
    eps_m: float,
    eps_days: float,
) -> NDArray[np.int64]:
    """Group detections of the same fire: linked if within eps_m AND eps_days of each other.

    Equivalent to space-time DBSCAN with min_samples=1 (single-linkage), so a fire that
    spreads over several days chains into one event.
    """
    tree = cKDTree(np.column_stack([x, y]))
    pairs = tree.query_pairs(r=eps_m, output_type="ndarray")
    if len(pairs):
        pairs = pairs[np.abs(t_days[pairs[:, 0]] - t_days[pairs[:, 1]]) <= eps_days]
    n = len(x)
    graph = sparse.coo_matrix(
        (np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])) if len(pairs) else ([], ([], [])),
        shape=(n, n),
    )
    _, labels = connected_components(graph, directed=False)
    return labels.astype(np.int64)


def ignitions(df: pd.DataFrame) -> pd.DataFrame:
    """One row per event: its earliest detection (ties broken by highest FRP).

    The first satellite detection is a proxy for the ignition location; it lags the real
    ignition by up to one overpass interval (~12 h), a limitation noted in the report.
    """
    ordered = df.sort_values(["event_id", "time", "frp"], ascending=[True, True, False])
    first = ordered.drop_duplicates("event_id").copy()
    first["n_detections"] = first["event_id"].map(df["event_id"].value_counts())
    return first.reset_index(drop=True)
