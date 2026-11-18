"""Step 08 — sensor-node and gateway placement for the pilot zone.

1. Risk on a 30 m grid: each pixel weighs (susceptibility of its 375 m cell) x (its
   wildland fraction from WorldCover 10 m). Pixels outside modelled wildland weigh 0.
2. Candidates: a 60 m lattice of wildland pixels within walking distance of a road/track.
3. Wind-aware coverage: full detection radius upwind, reduced downwind (ERA5-Land dominant
   summer wind over the pilot zone).
4. Greedy maximum coverage (>= 63% of optimal) up to `curve_max` nodes; the first `budget`
   are the deployment. Random placement of the same number of nodes is the baseline.
5. Gateways: hilltops near the access network; fewest masts such that every node has
   terrain line of sight to one (greedy set cover over DEM line-of-sight checks).

Outputs (data/processed/): nodes.geojson, gateways.geojson, coverage_curve.csv,
placement_metrics.json.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from rasterio.features import rasterize
from scipy.spatial import cKDTree

from placement.features import distance_to_mask, fill_nan_nearest
from placement.grid import Grid, aggregate_mean, pixel_centres
from placement.io import read_raster, step_main, write_json
from placement.optimise import (
    coverage_matrix,
    greedy_max_coverage,
    greedy_set_cover,
    random_baseline,
    wind_from_direction,
)
from placement.viewshed import local_peaks, visibility_matrix

log = logging.getLogger("placement.optimise")
WILDLAND = (10, 20, 30)  # WorldCover tree, shrub, grass


def _pilot_bbox_metric(cfg: dict[str, Any]) -> tuple[float, float, float, float]:
    to_utm = Transformer.from_crs(cfg["crs"]["storage"], cfg["crs"]["metric"], always_xy=True)
    w, s, e, n = cfg["pilot_zone"]["bbox"]
    xs, ys = to_utm.transform([w, e, e, w], [s, s, n, n])
    return min(xs), min(ys), max(xs), max(ys)


def _wind(cfg: dict[str, Any], box: tuple[float, float, float, float]) -> dict[str, float]:
    """Dominant summer wind over the pilot zone from ERA5-Land mean u/v components."""
    clim = read_raster(cfg["paths"]["raw"] / "gee" / "study_climate.tif")
    x, y = pixel_centres(clim.bands["wind_u"].shape, clim.transform)
    inside = (x >= box[0]) & (x <= box[2]) & (y >= box[1]) & (y <= box[3])
    u = float(np.nanmean(fill_nan_nearest(clim.bands["wind_u"])[inside]))
    v = float(np.nanmean(fill_nan_nearest(clim.bands["wind_v"])[inside]))
    speed = float(np.nanmean(fill_nan_nearest(clim.bands["wind_speed_ms"])[inside]))
    return {
        "from_deg": wind_from_direction(u, v),
        "mean_u": u,
        "mean_v": v,
        "mean_speed_ms": speed,
        # 1 = wind always from the same side, 0 = no preferred direction.
        "steadiness": float(np.hypot(u, v) / speed) if speed > 0 else 0.0,
    }


def run(cfg: dict[str, Any]) -> None:
    raw, interim, processed = (cfg["paths"][k] for k in ("raw", "interim", "processed"))
    oc, gc = cfg["optimise"], cfg["optimise"]["gateways"]
    name = cfg["pilot_zone"]["name"]
    metrics: dict[str, Any] = {
        "assumptions": {
            "detection_radius_m": oc["detection_radius_m"],
            "downwind_factor": oc["wind"]["downwind_factor"],
            "max_walk_to_track_m": oc["max_walk_to_track_m"],
            "min_node_spacing_m": oc["min_node_spacing_m"],
            "risk_field": oc["risk_field"],
            "gateway_range_m": gc["max_range_m"],
            "node_antenna_m": gc["node_antenna_m"],
            "gateway_antenna_m": gc["gateway_antenna_m"],
        }
    }

    # --- 1. risk on the 30 m pilot grid ---------------------------------------------------
    terrain = read_raster(raw / "gee" / f"{name}_terrain.tif")
    dem = terrain.bands["elevation"]
    t = terrain.transform
    px_m = float(t.a)
    g30 = Grid(x0=t.c, y0=t.f, cell=px_m, nrows=dem.shape[0], ncols=dem.shape[1])

    wc = read_raster(raw / "gee" / f"{name}_worldcover.tif")
    lc = wc.bands["Map"]
    wild10 = np.where(lc == 0, np.nan, np.isin(lc, WILDLAND).astype(float))
    wild30 = np.nan_to_num(aggregate_mean(wild10, wc.transform, g30), nan=0.0)

    g375 = Grid(**json.loads((interim / "grid.json").read_text(encoding="utf-8")))
    sus = pd.read_parquet(processed / "susceptibility.parquet")
    xc, yc = pixel_centres(dem.shape, t)
    r375, c375 = g375.index(xc.ravel(), yc.ravel())

    def to_pixels(field: str) -> np.ndarray:
        raster = g375.to_raster(sus.row.to_numpy(), sus.col.to_numpy(), sus[field].to_numpy())
        vals = np.where(r375 >= 0, raster[r375.clip(0), c375.clip(0)], np.nan)
        return vals.reshape(dem.shape)

    risk_px = to_pixels("susceptibility")  # reported per node
    pct_px = to_pixels("percentile")
    weight = np.nan_to_num(to_pixels(oc["risk_field"]), nan=0.0) * wild30

    # --- 2. candidates near the access network ---------------------------------------------
    fc = cfg["features"]
    box = _pilot_bbox_metric(cfg)
    pad = 0.02
    w_, s_, e_, n_ = cfg["pilot_zone"]["bbox"]
    roads = gpd.read_file(
        raw / "osm" / "gis_osm_roads_free_1.shp",
        bbox=(w_ - pad, s_ - pad, e_ + pad, n_ + pad),
        columns=["fclass"],
    ).to_crs(cfg["crs"]["metric"])
    access = roads[roads.fclass.isin(fc["road_classes"] + fc["track_classes"])]
    access_mask = rasterize(
        ((geom, 1) for geom in access.geometry), out_shape=dem.shape, transform=t, all_touched=True
    ).astype(bool)
    dist_access = distance_to_mask(access_mask, px_m)

    step = max(1, round(oc["candidate_spacing_m"] / px_m))
    lattice = np.zeros(dem.shape, dtype=bool)
    lattice[::step, ::step] = True
    cand = (
        lattice
        & (dist_access <= oc["max_walk_to_track_m"])
        & (wild30 >= oc["min_candidate_wildland"])
        & ~np.isnan(dem)
    )
    cr, cc = np.nonzero(cand)
    tr, tc_ = np.nonzero(weight > 0)
    cand_xy = np.column_stack([xc[cr, cc], yc[cr, cc]])
    targ_xy = np.column_stack([xc[tr, tc_], yc[tr, tc_]])
    targ_w = weight[tr, tc_]
    total = float(targ_w.sum())
    log.info(
        "pilot grid %dx%d at %.0f m: %d risk pixels, %d candidate sites (%d OSM access segments)",
        dem.shape[0],
        dem.shape[1],
        px_m,
        len(targ_w),
        len(cr),
        len(access),
    )

    # --- 3-4. wind-aware greedy coverage ------------------------------------------------
    wind = _wind(cfg, box) if oc["wind"]["enabled"] else {"from_deg": None}
    wind_from = wind["from_deg"] if oc["wind"]["enabled"] else None
    metrics["wind"] = wind
    log.info("dominant summer wind: %s", {k: round(v, 3) for k, v in wind.items() if v is not None})
    cov = coverage_matrix(
        cand_xy,
        targ_xy,
        oc["detection_radius_m"],
        wind_from_deg=wind_from,
        downwind_factor=oc["wind"]["downwind_factor"],
    )
    greedy = greedy_max_coverage(
        cov,
        targ_w,
        k=oc["curve_max"],
        candidates_xy=cand_xy,
        min_spacing_m=oc["min_node_spacing_m"],
    )
    share = greedy.cumulative_covered / total

    curve_n = np.arange(1, len(share) + 1)
    curve = pd.DataFrame({"n_nodes": curve_n, "risk_covered_share": share})
    marks = {}
    for n in oc["curve_marks"]:
        if n > len(share):
            continue
        base = random_baseline(
            cov, targ_w, n=n, repeats=oc["random_repeats"], seed=cfg["model"]["seed"]
        )
        marks[str(n)] = {
            "greedy_share": float(share[n - 1]),
            "random_share_mean": base["mean"] / total,
            "random_share_std": base["std"] / total,
            "lift_vs_random": float(share[n - 1] / (base["mean"] / total))
            if base["mean"]
            else None,
        }
        log.info(
            "%4d nodes: greedy covers %.2f%% of pilot risk, random %.2f%% (x%.1f)",
            n,
            100 * share[n - 1],
            100 * base["mean"] / total,
            marks[str(n)]["lift_vs_random"] or 0,
        )
    curve.to_csv(processed / "coverage_curve.csv", index=False)
    metrics["coverage"] = marks
    metrics["pilot"] = {
        "risk_pixels": int(len(targ_w)),
        "candidate_sites": int(len(cr)),
        "wildland_km2": float(wild30.sum() * px_m**2 / 1e6),
        "footprint_km2_per_node_upwind": float(np.pi * oc["detection_radius_m"] ** 2 / 1e6),
    }

    budget = min(oc["budget"], len(greedy.selected))
    sel = np.asarray(greedy.selected[:budget])
    nr, nc = cr[sel], cc[sel]
    marginal = np.diff(np.concatenate([[0.0], greedy.cumulative_covered[:budget]])) / total

    # --- 5. gateways --------------------------------------------------------------------
    window = int(round(gc["peak_window_m"] / px_m)) | 1  # odd window
    pr, pc = local_peaks(dem, window, gc["peak_min_percentile"])
    near = dist_access[pr, pc] <= gc["max_dist_to_access_m"]
    pr, pc = pr[near], pc[near]
    vis = visibility_matrix(
        dem,
        px_m,
        np.column_stack([pr, pc]),
        np.column_stack([nr, nc]),
        gateway_h=gc["gateway_antenna_m"],
        node_h=gc["node_antenna_m"],
        max_range_m=gc["max_range_m"],
        earth_k=gc["earth_k_factor"],
    )
    cover = greedy_set_cover(vis)
    gw = np.asarray(cover.selected)
    log.info(
        "gateways: %d hilltop candidates, %d chosen, %d nodes without line of sight",
        len(pr),
        len(gw),
        len(cover.uncovered),
    )

    # Assign each node to the nearest chosen gateway it can see.
    vis_sel = vis[gw].toarray() if len(gw) else np.zeros((0, len(sel)), dtype=bool)
    gw_x, gw_y = xc[pr[gw], pc[gw]], yc[pr[gw], pc[gw]]
    node_x, node_y = xc[nr, nc], yc[nr, nc]
    assigned = np.full(len(sel), -1)
    for j in range(len(sel)):
        seen = np.flatnonzero(vis_sel[:, j])
        if len(seen):
            d = np.hypot(gw_x[seen] - node_x[j], gw_y[seen] - node_y[j])
            assigned[j] = int(seen[np.argmin(d)])

    crs_m, crs_ll = cfg["crs"]["metric"], cfg["crs"]["storage"]
    nodes = gpd.GeoDataFrame(
        {
            "node_id": np.arange(1, len(sel) + 1),
            "rank": np.arange(1, len(sel) + 1),
            "marginal_risk_share": marginal,
            "cumulative_risk_share": share[:budget],
            "susceptibility": risk_px[nr, nc],
            "risk_percentile": pct_px[nr, nc],
            "elevation_m": dem[nr, nc],
            "dist_to_access_m": dist_access[nr, nc],
            "gateway_id": np.where(assigned >= 0, assigned + 1, 0),
        },
        geometry=gpd.points_from_xy(node_x, node_y),
        crs=crs_m,
    ).to_crs(crs_ll)
    gateways = gpd.GeoDataFrame(
        {
            "gateway_id": np.arange(1, len(gw) + 1),
            "elevation_m": dem[pr[gw], pc[gw]],
            "dist_to_access_m": dist_access[pr[gw], pc[gw]],
            "nodes_assigned": [int((assigned == k).sum()) for k in range(len(gw))],
            "nodes_in_view": vis_sel.sum(axis=1).astype(int) if len(gw) else [],
        },
        geometry=gpd.points_from_xy(gw_x, gw_y),
        crs=crs_m,
    ).to_crs(crs_ll)
    nodes.to_file(processed / "nodes.geojson", driver="GeoJSON")
    gateways.to_file(processed / "gateways.geojson", driver="GeoJSON")

    metrics["nodes"] = {
        "n": int(len(sel)),
        "median_dist_to_access_m": float(np.median(dist_access[nr, nc])),
        "median_susceptibility": float(np.nanmedian(risk_px[nr, nc])),
        "median_risk_percentile": float(np.nanmedian(pct_px[nr, nc])),
        "share_in_national_top10pct": float(np.mean(pct_px[nr, nc] >= 90)),
        "median_spacing_to_nearest_node_m": float(
            np.median(
                cKDTree(np.column_stack([node_x, node_y])).query(
                    np.column_stack([node_x, node_y]), k=2
                )[0][:, 1]
            )
        )
        if len(sel) > 1
        else None,
        "pilot_median_susceptibility": float(np.nanmedian(risk_px[weight > 0])),
    }
    metrics["gateways"] = {
        "n": int(len(gw)),
        "candidates": int(len(pr)),
        "nodes_without_line_of_sight": len(cover.uncovered),
    }
    write_json(processed / "placement_metrics.json", metrics)
    log.info("placement metrics: %s", json.dumps(metrics, indent=1))


if __name__ == "__main__":
    step_main(run, "Step 08 - node and gateway placement")
