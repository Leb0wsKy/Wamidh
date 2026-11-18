"""Shared helpers for report figures and headline numbers (CLAUDE.md §6.3)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from numpy.typing import NDArray

ACCENT = "#B3261E"  # Wamidh red: our result / wildfire
COMPARE = "#2a78d6"  # comparison, baseline, sensor sites on red maps
THIRD = "#C98500"  # third class (low contrast: always labelled)
CONTEXT = "#BDBDBD"  # background context only
INK = "#1a1a19"
INK_2 = "#52514e"

FEATURE_LABELS = {
    "elevation_m": "Elevation",
    "slope_deg": "Slope",
    "aspect_sin": "Aspect (east-west)",
    "aspect_cos": "Aspect (north-south)",
    "lc_tree": "Tree cover share",
    "lc_shrub": "Shrubland share",
    "lc_grass": "Grassland share",
    "lc_crop": "Cropland share",
    "lc_built": "Built-up share",
    "ndvi_summer": "Summer NDVI",
    "tmax_c": "Summer max. temperature",
    "wind_speed_ms": "Summer wind speed",
    "precip_mm_yr": "Annual precipitation",
    "dist_road_m": "Distance to road",
    "dist_track_m": "Distance to track",
    "dist_path_m": "Distance to footpath",
    "dist_place_m": "Distance to village (OSM)",
    "dist_builtup_m": "Distance to built-up land",
    "dist_cropland_m": "Distance to cropland",
    "hist_ign_1km": "Past fire starts within 1 km",
    "hist_ign_5km": "Past fire starts within 5 km",
    "hist_det_1km": "Past fire detections within 1 km",
    "dist_hist_ign_m": "Distance to nearest past fire start",
}


def feature_label(name: str) -> str:
    return FEATURE_LABELS.get(name, name)


def risk_cmap() -> LinearSegmentedColormap:
    """Single-hue sequential ramp: soft Wamidh pink -> accent red -> dark red."""
    return LinearSegmentedColormap.from_list(
        "wamidh_risk", ["#F4E9E7", "#E6B3AA", "#CF6F61", ACCENT, "#6B1611"]
    )


def save_figure(fig: Figure, name: str, out_dir: Path) -> list[Path]:
    """Report export: PNG at 300 dpi and SVG, same name."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"{name}.png", out_dir / f"{name}.svg"]
    fig.savefig(paths[0], dpi=300)
    fig.savefig(paths[1])
    return paths


def high_risk_access_share(
    percentile: NDArray[np.float64],
    dist_road: NDArray[np.float64],
    dist_track: NDArray[np.float64],
    min_percentile: float,
    max_dist_m: float,
) -> float:
    """Share of high-risk cells whose centre lies within `max_dist_m` of a road or track."""
    high = percentile >= min_percentile
    near = np.minimum(dist_road, dist_track) <= max_dist_m
    return float(near[high].mean()) if high.any() else float("nan")
