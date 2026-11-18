"""Step 09 — report figures (PNG 300 dpi + SVG) and headline numbers.

Figures (docs/figures/):
  fig_firms_map          cleaned FIRMS detections over northern Tunisia
  fig_risk_map_north     ignition-susceptibility map, northern Tunisia
  fig_risk_map_pilot     Kroumirie susceptibility with sensor nodes and gateways
  fig_coverage_curve     pilot risk within detection range vs number of nodes, vs random
  fig_shap               SHAP summary of the final model
  fig_model_comparison   spatial vs random cross-validation, per model
  fig_capture_curve      share of future fire starts vs share of wildland flagged
  fig_calibration        reliability diagram, raw vs calibrated

Numbers: docs/figures/metrics.json. Captions: docs/figures/README.md.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import rasterio  # noqa: E402
import shap  # noqa: E402
import shapely  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from pyproj import Transformer  # noqa: E402

from placement.fires import filter_detections  # noqa: E402
from placement.io import step_main, write_json  # noqa: E402
from placement.model import capture_rate  # noqa: E402
from placement.report import (  # noqa: E402
    ACCENT,
    COMPARE,
    CONTEXT,
    INK,
    INK_2,
    THIRD,
    feature_label,
    high_risk_access_share,
    risk_cmap,
    save_figure,
)

log = logging.getLogger("placement.figures")
# OSM names in the pilot zone are in Arabic script, which matplotlib cannot shape;
# the report figures use the usual Latin spellings.
TOWN_LABELS = {"طبرقة": "Tabarka", "عين دراهم": "Aïn Draham", "فرنانة": "Fernana"}
MODEL_LABELS = {
    "logistic": "Logistic regression",
    "random_forest": "Random forest",
    "lightgbm": "LightGBM",
    "xgboost": "XGBoost",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _clean_axes(ax: plt.Axes) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)


def _scale_bar(ax: plt.Axes, length_m: float, label: str) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    x = x1 - 0.05 * (x1 - x0) - length_m
    y = y0 + 0.05 * (y1 - y0)
    ax.plot([x, x + length_m], [y, y], color=INK, lw=2, solid_capstyle="butt")
    ax.text(x + length_m / 2, y + 0.015 * (y1 - y0), label, ha="center", va="bottom", fontsize=7)


def _pilot_box_metric(cfg: dict[str, Any]) -> tuple[list[float], list[float]]:
    to_utm = Transformer.from_crs(cfg["crs"]["storage"], cfg["crs"]["metric"], always_xy=True)
    w, s, e, n = cfg["pilot_zone"]["bbox"]
    xs, ys = to_utm.transform([w, e, e, w, w], [s, s, n, n, s])
    return list(xs), list(ys)


# --- figures ------------------------------------------------------------------


def fig_firms_map(cfg: dict[str, Any], out: Path, m: dict[str, Any]) -> None:
    interim, raw = cfg["paths"]["interim"], cfg["paths"]["raw"]
    gov = gpd.read_file(raw / "boundaries" / "tun_adm1.geojson")
    tunisia = gov.union_all()
    every = pd.read_parquet(interim / "fires_all.parquet")
    every = every[shapely.contains_xy(tunisia, every.lon.to_numpy(), every.lat.to_numpy())]
    passed = filter_detections(every.reset_index(drop=True), cfg["fires"])
    clean = pd.read_parquet(interim / "fires_clean.parquet")
    key = ["source", "lat", "lon", "time"]
    crop = passed.merge(clean[key], on=key, how="left", indicator=True)
    crop = crop[crop["_merge"] == "left_only"]
    n_other = len(every) - len(passed)

    w, s, e, n = cfg["study_area"]["bbox"]
    fig, ax = plt.subplots(figsize=(6.5, 5.6))
    gov.boundary.plot(ax=ax, color="#9a9a96", lw=0.4)
    ax.scatter(every.lon, every.lat, s=0.6, c=CONTEXT, lw=0, rasterized=True)
    ax.scatter(crop.lon, crop.lat, s=0.8, c=THIRD, lw=0, rasterized=True)
    ax.scatter(clean.lon, clean.lat, s=0.8, c=ACCENT, lw=0, rasterized=True)
    pw, ps, pe, pn = cfg["pilot_zone"]["bbox"]
    ax.plot([pw, pe, pe, pw, pw], [ps, ps, pn, pn, ps], color=INK, lw=1)
    ax.text(pw, pn + 0.03, "Kroumirie pilot", fontsize=7, color=INK)
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(1 / np.cos(np.deg2rad((s + n) / 2)))
    _clean_axes(ax)
    handles = [
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=5,
            color=ACCENT,
            label=f"Kept: wildland fire detections ({len(clean):,})",
        ),
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=5,
            color=THIRD,
            label=f"Removed: on cropland ({len(crop):,})",
        ),
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=5,
            color=CONTEXT,
            label=f"Removed: low confidence, weak, industrial or off-season ({n_other:,})",
        ),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 0.0), fontsize=7)
    ax.set_title("NASA FIRMS active-fire detections in Tunisia, May–October 2001–2025", loc="left")
    fig.text(
        0.01,
        0.01,
        "Source: NASA FIRMS (VIIRS S-NPP 375 m 2012–2025, MODIS 1 km 2001–2025); "
        "boundaries: geoBoundaries.",
        fontsize=6,
        color=INK_2,
    )
    save_figure(fig, "fig_firms_map", out)
    plt.close(fig)
    m["fires"] = {
        "detections_in_tunisia_box": int(len(every)),
        "removed_quality_or_type": int(n_other),
        "removed_cropland": int(len(crop)),
        "kept": int(len(clean)),
        "events": int(clean.event_id.nunique()),
    }


def _risk_raster(path: Path) -> tuple[np.ndarray, Any]:
    with rasterio.open(path) as r:
        return r.read(2), r.bounds


def fig_risk_map_north(cfg: dict[str, Any], out: Path) -> None:
    a, b = _risk_raster(cfg["paths"]["processed"] / "susceptibility_north.tif")
    gov = gpd.read_file(cfg["paths"]["raw"] / "boundaries" / "tun_adm1.geojson").to_crs(
        cfg["crs"]["metric"]
    )
    fig, ax = plt.subplots(figsize=(6.8, 4.9))
    im = ax.imshow(
        a,
        extent=(b.left, b.right, b.bottom, b.top),
        cmap=risk_cmap(),
        vmin=0,
        vmax=100,
        interpolation="nearest",
    )
    gov.boundary.plot(ax=ax, color="#7a7a76", lw=0.4)
    px, py = _pilot_box_metric(cfg)
    ax.plot(px, py, color=INK, lw=1)
    ax.text(px[0], py[2] + 3000, "Kroumirie pilot", fontsize=7)
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(b.bottom, b.top)
    _clean_axes(ax)
    _scale_bar(ax, 50_000, "50 km")
    cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("Ignition susceptibility (percentile among wildland cells)")
    cb.outline.set_visible(False)
    ax.set_title("Where wildfires start: ignition susceptibility, northern Tunisia", loc="left")
    fig.text(
        0.01,
        0.01,
        "375 m cells with ≥30% tree, shrub or grass cover; white = not modelled "
        "(cropland, towns, water). Random forest, fire history 2010–2025.",
        fontsize=6,
        color=INK_2,
    )
    save_figure(fig, "fig_risk_map_north", out)
    plt.close(fig)


def fig_risk_map_pilot(cfg: dict[str, Any], out: Path) -> None:
    processed, raw = cfg["paths"]["processed"], cfg["paths"]["raw"]
    a, b = _risk_raster(processed / f"susceptibility_{cfg['pilot_zone']['name']}.tif")
    crs = cfg["crs"]["metric"]
    nodes = gpd.read_file(processed / "nodes.geojson").to_crs(crs)
    gws = gpd.read_file(processed / "gateways.geojson").to_crs(crs)
    w, s, e, n = cfg["pilot_zone"]["bbox"]
    places = gpd.read_file(raw / "osm" / "gis_osm_places_free_1.shp", bbox=(w, s, e, n))
    places = places[places.fclass.isin(["town", "city"])].to_crs(crs)

    fig, ax = plt.subplots(figsize=(6.8, 6.0))
    im = ax.imshow(
        a,
        extent=(b.left, b.right, b.bottom, b.top),
        cmap=risk_cmap(),
        vmin=0,
        vmax=100,
        interpolation="nearest",
    )
    gpos = gws.set_index("gateway_id").geometry
    for _, row in nodes[nodes.gateway_id > 0].iterrows():
        g = gpos[row.gateway_id]
        ax.plot([row.geometry.x, g.x], [row.geometry.y, g.y], color="#4d4d4a", lw=0.35, zorder=2)
    ax.scatter(
        nodes.geometry.x, nodes.geometry.y, s=14, c=COMPARE, edgecolors="white", lw=0.6, zorder=3
    )
    no_los = nodes[nodes.gateway_id == 0]
    ax.scatter(
        no_los.geometry.x,
        no_los.geometry.y,
        s=60,
        facecolors="none",
        edgecolors=COMPARE,
        lw=1.2,
        zorder=3,
    )
    ax.scatter(
        gws.geometry.x,
        gws.geometry.y,
        s=60,
        marker="^",
        c=INK,
        edgecolors="white",
        lw=0.8,
        zorder=4,
    )
    for _, p in places.iterrows():
        label = TOWN_LABELS.get(p.get("name"))
        if label:
            ax.annotate(
                label,
                (p.geometry.x, p.geometry.y),
                fontsize=7,
                color=INK,
                xytext=(4, 4),
                textcoords="offset points",
                zorder=5,
                bbox={"boxstyle": "round,pad=0.15", "fc": "white", "ec": "none", "alpha": 0.8},
            )
    ax.set_xlim(b.left, b.right)
    ax.set_ylim(b.bottom, b.top)
    _clean_axes(ax)
    _scale_bar(ax, 10_000, "10 km")
    handles = [
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=5,
            color=COMPARE,
            mec="white",
            label=f"Sensor node ({len(nodes)})",
        ),
        Line2D(
            [],
            [],
            ls="",
            marker="^",
            ms=7,
            color=INK,
            mec="white",
            label=f"Gateway on a hilltop ({len(gws)})",
        ),
        Line2D([], [], color="#4d4d4a", lw=0.8, label="Radio line of sight"),
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=8,
            mfc="none",
            mec=COMPARE,
            label=f"Node without line of sight ({len(no_los)})",
        ),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=2, fontsize=7)
    cb = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cb.set_label("Ignition susceptibility (percentile, national)")
    cb.outline.set_visible(False)
    ax.set_title("Kroumirie pilot: optimised sensor sites and gateways", loc="left")
    oc, gc = cfg["optimise"], cfg["optimise"]["gateways"]
    fig.text(
        0.01,
        0.01,
        f"Nodes ≥{oc['min_node_spacing_m'] / 1000:.0f} km apart, ≤{oc['max_walk_to_track_m']} m "
        f"from a road or track; gateways on hilltops ≤{gc['max_dist_to_access_m'] / 1000:.0f} "
        f"km from access, LoRa range {gc['max_range_m'] / 1000:.0f} km (assumption), "
        "line of sight on SRTM 30 m.",
        fontsize=6,
        color=INK_2,
    )
    save_figure(fig, "fig_risk_map_pilot", out)
    plt.close(fig)


def fig_coverage_curve(cfg: dict[str, Any], out: Path, pm: dict[str, Any]) -> None:
    curve = pd.read_csv(cfg["paths"]["processed"] / "coverage_curve.csv")
    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    ax.plot(
        curve.n_nodes, 100 * curve.risk_covered_share, color=ACCENT, label="Wamidh placement"
    )
    marks = pm["coverage"]
    xs = [int(k) for k in marks]
    ax.errorbar(
        xs,
        [100 * marks[k]["random_share_mean"] for k in marks],
        yerr=[100 * marks[k]["random_share_std"] for k in marks],
        fmt="o",
        ms=6,
        color=COMPARE,
        capsize=0,
        lw=1.2,
        label="Random placement (mean ± 1 sd)",
    )
    for k in marks:
        ax.plot(int(k), 100 * marks[k]["greedy_share"], "o", ms=6, color=ACCENT)
    summary = "\n".join(
        f"{int(k):>4} nodes: ×{marks[k]['lift_vs_random']:.1f} the risk of random sites"
        for k in marks
    )
    ax.text(
        0.97, 0.05, summary, transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color=INK
    )
    ax.set_xlabel("Number of sensor nodes")
    ax.set_ylabel("Pilot risk within detection range (%)")
    ax.set_xlim(0, curve.n_nodes.max())
    ax.set_ylim(0, None)
    ax.legend(loc="upper left")
    oc = cfg["optimise"]
    ax.set_title("Risk reached per node: optimised vs random sites", loc="left")
    fig.text(
        0.01,
        -0.02,
        f"Detection radius {oc['detection_radius_m']} m upwind, "
        f"{oc['detection_radius_m'] * oc['wind']['downwind_factor']:.0f} m downwind (assumptions); "
        f"nodes ≥{oc['min_node_spacing_m']} m apart. "
        "Goal: well-chosen sites, not blanket coverage.",
        fontsize=6,
        color=INK_2,
    )
    save_figure(fig, "fig_coverage_curve", out)
    plt.close(fig)


def fig_shap(cfg: dict[str, Any], out: Path, tm: dict[str, Any]) -> None:
    interim, processed = cfg["paths"]["interim"], cfg["paths"]["processed"]
    sv = pd.read_parquet(processed / "shap_values.parquet")
    labels = pd.read_parquet(interim / "labels.parquet")[["cell_id"]]
    X = (
        labels.merge(pd.read_parquet(interim / "features.parquet"), on="cell_id")
        .merge(pd.read_parquet(interim / "history_train.parquet"), on="cell_id")
        .set_index("cell_id")
        .loc[sv.cell_id]
    )
    feats = tm["features"]
    cmap = LinearSegmentedColormap.from_list("shap", ["#E6B3AA", ACCENT, "#6B1611"])
    shap.summary_plot(
        sv[feats].to_numpy(),
        X[feats].to_numpy(),
        feature_names=[feature_label(f) for f in feats],
        max_display=12,
        cmap=cmap,
        show=False,
        plot_size=(6.8, 4.8),
        color_bar_label="Feature value",
    )
    fig = plt.gcf()
    fig.axes[0].set_xlabel("SHAP value (impact on predicted ignition risk)", fontsize=9)
    fig.axes[0].tick_params(labelsize=8)
    fig.axes[-1].tick_params(labelsize=8)
    fig.axes[-1].set_ylabel("Feature value", fontsize=8)
    fig.axes[0].set_title(
        f"What drives ignition risk ({MODEL_LABELS.get(tm['shap_model'], tm['shap_model'])})",
        loc="left",
        fontsize=10,
        fontweight="bold",
    )
    save_figure(fig, "fig_shap", out)
    plt.close(fig)


def fig_model_comparison(out: Path, tm: dict[str, Any]) -> None:
    names = list(tm["models"])
    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    for i, n in enumerate(names):
        sp = tm["models"][n]["spatial_cv"]
        rnd = tm["models"][n]["random_cv"]["pooled"]["roc_auc"]
        ax.plot([sp["mean_fold_roc_auc"], rnd], [i, i], color="#cfcfcb", lw=2, zorder=1)
        ax.errorbar(
            sp["mean_fold_roc_auc"],
            i,
            xerr=sp["std_fold_roc_auc"],
            fmt="o",
            ms=8,
            color=ACCENT,
            lw=1.2,
            capsize=0,
            zorder=3,
        )
        ax.plot(rnd, i, "o", ms=8, color=COMPARE, zorder=3)
        ax.annotate(
            f"{sp['mean_fold_roc_auc']:.3f}",
            (sp["mean_fold_roc_auc"], i),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
        ax.annotate(
            f"{rnd:.3f}",
            (rnd, i),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    ax.set_yticks(range(len(names)), [MODEL_LABELS.get(n, n) for n in names])
    ax.set_ylim(-0.6, len(names) - 0.4)
    ax.axvline(0.5, color="#9a9a96", lw=0.8)
    ax.text(0.502, len(names) - 0.5, "chance", fontsize=7, color=INK_2, va="top")
    ax.set_xlim(0.45, 0.9)
    ax.set_xlabel("ROC-AUC")
    ax.grid(axis="y", visible=False)
    handles = [
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=7,
            color=ACCENT,
            label="Spatial CV: held-out governorates (honest; ± 1 sd across folds)",
        ),
        Line2D(
            [],
            [],
            ls="",
            marker="o",
            ms=7,
            color=COMPARE,
            label="Random split (leaks neighbouring cells; not used for selection)",
        ),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22), fontsize=7)
    ax.set_title("Model comparison: random splits overstate skill", loc="left")
    save_figure(fig, "fig_model_comparison", out)
    plt.close(fig)


def fig_capture_curve(
    cfg: dict[str, Any], out: Path, tm: dict[str, Any], m: dict[str, Any]
) -> None:
    oof = pd.read_parquet(cfg["paths"]["processed"] / "oof_predictions.parquet")
    y, p = oof.label.to_numpy(), oof[f"oof_{tm['best_model']}"].to_numpy()
    shares = np.linspace(0.01, 1.0, 100)
    cap = capture_rate(y, p, list(shares))
    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    ax.plot([0, 100], [0, 100], color="#9a9a96", lw=1, label="Random ranking")
    ax.plot(
        [0, *(100 * shares)],
        [0, *(100 * np.array(list(cap.values())))],
        color=ACCENT,
        label=f"{MODEL_LABELS.get(tm['best_model'], tm['best_model'])} (held-out regions)",
    )
    key = capture_rate(y, p, [0.1, 0.2, 0.3])
    for s, c in key.items():
        ax.plot(100 * s, 100 * c, "o", ms=6, color=ACCENT)
        ax.annotate(
            f"{100 * c:.0f}% of fire starts in\nriskiest {100 * s:.0f}% of wildland",
            (100 * s, 100 * c),
            xytext=(8, -18),
            textcoords="offset points",
            fontsize=7,
        )
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.set_xlabel("Share of wildland flagged, riskiest first (%)")
    ax.set_ylabel("Share of 2017–2025 fire starts captured (%)")
    ax.legend(loc="lower right")
    ax.set_title("Future fire starts captured by the risk ranking", loc="left")
    save_figure(fig, "fig_capture_curve", out)
    plt.close(fig)
    m["model"]["capture"] = {f"top_{int(100 * s)}pct_land": c for s, c in key.items()}


def fig_calibration(out: Path, tm: dict[str, Any]) -> None:
    c = tm["calibration"]
    fig, ax = plt.subplots(figsize=(4.6, 4.4))
    ax.plot([0, 1], [0, 1], color="#9a9a96", lw=1, label="Perfect calibration")
    for key, color, label in [
        ("curve_raw", COMPARE, "Raw model score"),
        ("curve_calibrated", ACCENT, "After isotonic calibration"),
    ]:
        pts = c[key]
        ax.plot(
            [q["mean_pred"] for q in pts],
            [q["frac_pos"] for q in pts],
            "o-",
            color=color,
            ms=6,
            label=label,
        )
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability (balanced sample)")
    ax.set_ylabel("Observed share of fire cells")
    ax.legend(loc="upper left")
    ax.set_title(
        f"Calibration (Brier {c['brier_raw']:.3f} → {c['brier_calibrated']:.3f})", loc="left"
    )
    save_figure(fig, "fig_calibration", out)
    plt.close(fig)


# --- numbers ---------------------------------------------------------------------


def headline_numbers(
    cfg: dict[str, Any], tm: dict[str, Any], pm: dict[str, Any], m: dict[str, Any]
) -> None:
    interim, processed = cfg["paths"]["interim"], cfg["paths"]["processed"]
    best = tm["best_model"]
    sp = tm["models"][best]["spatial_cv"]
    m["model"].update(
        {
            "best_model": best,
            "validation": "leave-one-governorate-out; labels 2017-2025, fire history 2001-2016",
            "spatial_cv_mean_fold_roc_auc": sp["mean_fold_roc_auc"],
            "spatial_cv_std_fold_roc_auc": sp["std_fold_roc_auc"],
            "spatial_cv_pooled_pr_auc": sp["pooled"]["pr_auc"],
            "random_cv_roc_auc": tm["models"][best]["random_cv"]["pooled"]["roc_auc"],
            "calibrated_precision_at_0.5": tm["calibration"]["scores_at_threshold"]["precision"],
            "calibrated_recall_at_0.5": tm["calibration"]["scores_at_threshold"]["recall"],
            "brier_raw": tm["calibration"]["brier_raw"],
            "brier_calibrated": tm["calibration"]["brier_calibrated"],
            "top_features_shap": {feature_label(k): v for k, v in tm["shap_mean_abs_top"].items()},
            "top_features_permutation": {
                feature_label(k): v for k, v in tm["permutation_importance_top"].items()
            },
            "all_models_spatial_roc_auc": {
                n: v["spatial_cv"]["mean_fold_roc_auc"] for n, v in tm["models"].items()
            },
        }
    )
    m["placement"] = {
        "nodes": pm["nodes"]["n"],
        "gateways": pm["gateways"]["n"],
        "nodes_without_line_of_sight": pm["gateways"]["nodes_without_line_of_sight"],
        "node_sites_median_risk_percentile": pm["nodes"]["median_risk_percentile"],
        "node_sites_share_in_national_top10pct": pm["nodes"]["share_in_national_top10pct"],
        "median_dist_to_road_or_track_m": pm["nodes"]["median_dist_to_access_m"],
        "median_spacing_between_nodes_m": pm["nodes"]["median_spacing_to_nearest_node_m"],
        "risk_within_detection_range": {
            k: {
                "optimised": v["greedy_share"],
                "random": v["random_share_mean"],
                "lift": v["lift_vs_random"],
            }
            for k, v in pm["coverage"].items()
        },
        "wind_from_deg": pm["wind"]["from_deg"],
        "wind_steadiness": pm["wind"]["steadiness"],
    }
    # Share of the pilot's high-risk wildland within walking distance of a road or track
    # (375 m cell centres; supports the deployability / market-size argument).
    sus = pd.read_parquet(processed / "susceptibility.parquet")
    feats = pd.read_parquet(interim / "features.parquet")[
        ["cell_id", "dist_road_m", "dist_track_m"]
    ]
    w, s, e, n = cfg["pilot_zone"]["bbox"]
    pilot = sus[sus.lon.between(w, e) & sus.lat.between(s, n)].merge(feats, on="cell_id")
    walk = cfg["optimise"]["max_walk_to_track_m"]
    for pct in (80, 90):
        m["placement"][f"pilot_top{100 - pct}pct_cells_within_{walk}m_of_access"] = (
            high_risk_access_share(
                pilot.percentile.to_numpy(),
                pilot.dist_road_m.to_numpy(),
                pilot.dist_track_m.to_numpy(),
                min_percentile=pct,
                max_dist_m=walk,
            )
        )
    m["assumptions"] = pm["assumptions"] | {
        "wildland_min_fraction_per_cell": cfg["grid"]["min_wildland_fraction"],
        "fire_event_link_m_days": [
            cfg["fires"]["dbscan"]["eps_m"],
            cfg["fires"]["dbscan"]["eps_days"],
        ],
    }
    experiments = {}
    for name in [
        "tuning_random_forest",
        "tuning_lightgbm",
        "tuning_xgboost",
        "local_vs_global",
        "fire_history",
    ]:
        data = _read_json(processed / f"{name}.json")
        if data is None:
            continue
        if name.startswith("tuning_"):
            experiments[name] = {
                k: data[k] for k in ("untuned_mean_fold_roc_auc", "tuned_mean_fold_roc_auc")
            }
        elif name == "local_vs_global":
            experiments[name] = {
                mdl: {a: v["mean_roc_auc"] for a, v in r.items()}
                for mdl, r in data["results"].items()
            }
        else:
            experiments[name] = {
                k: {"roc_auc": v["mean_fold_roc_auc"], "capture": v["capture"]}
                for k, v in data["results"].items()
            }
    experiments["_setup_notes"] = {
        "tuning_*, local_vs_global": (
            "run before fire history was adopted: labels = all fire starts 2001-2025, static "
            "features only. Compare within the experiment, not with the final model's score."
        ),
        "fire_history": (
            "the experiment that led to the final setup (history 2001-2016, labels 2017-2025)."
        ),
    }
    m["experiments"] = experiments


def run(cfg: dict[str, Any]) -> None:
    out = cfg["paths"]["figures"]
    plt.style.use(cfg["paths"]["style"])
    processed = cfg["paths"]["processed"]
    tm = _read_json(processed / "train_metrics.json")
    pm = _read_json(processed / "placement_metrics.json")
    if tm is None or pm is None:
        raise SystemExit("Run steps 06 and 08 first.")
    m: dict[str, Any] = {
        "note": "Generated by placement step 09; do not edit by hand.",
        "model": {},
    }

    for name, fn in [
        ("fig_firms_map", lambda: fig_firms_map(cfg, out, m)),
        ("fig_risk_map_north", lambda: fig_risk_map_north(cfg, out)),
        ("fig_risk_map_pilot", lambda: fig_risk_map_pilot(cfg, out)),
        ("fig_coverage_curve", lambda: fig_coverage_curve(cfg, out, pm)),
        ("fig_shap", lambda: fig_shap(cfg, out, tm)),
        ("fig_model_comparison", lambda: fig_model_comparison(out, tm)),
        ("fig_capture_curve", lambda: fig_capture_curve(cfg, out, tm, m)),
        ("fig_calibration", lambda: fig_calibration(out, tm)),
    ]:
        fn()
        log.info("wrote %s (.png, .svg)", name)
    headline_numbers(cfg, tm, pm, m)
    write_json(out / "metrics.json", m)
    log.info("wrote metrics.json")


if __name__ == "__main__":
    step_main(run, "Step 09 - report figures and metrics")
