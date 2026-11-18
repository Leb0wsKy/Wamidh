from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from placement.report import (  # noqa: E402
    feature_label,
    high_risk_access_share,
    risk_cmap,
    save_figure,
)


def test_risk_cmap_gets_strictly_darker() -> None:
    rgb = risk_cmap()(np.linspace(0, 1, 11))[:, :3]
    luminance = rgb @ np.array([0.2126, 0.7152, 0.0722])

    assert np.all(np.diff(luminance) < 0)


def test_save_figure_writes_png_and_svg(tmp_path: Path) -> None:
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])

    paths = save_figure(fig, "fig_test", tmp_path)

    assert sorted(p.name for p in paths) == ["fig_test.png", "fig_test.svg"]
    assert all(p.stat().st_size > 0 for p in paths)


def test_high_risk_access_share_counts_cells_near_road_or_track() -> None:
    pct = np.array([95, 90, 85, 50, 99])
    road = np.array([100, 800, 900, 10, 2000])
    track = np.array([900, 200, 700, 10, 2000])

    share = high_risk_access_share(pct, road, track, min_percentile=80, max_dist_m=300)

    # High-risk cells: 0, 1, 2, 4. Near access: 0 (road), 1 (track) -> 2 of 4.
    assert share == 0.5


def test_feature_label_is_readable_with_fallback() -> None:
    assert feature_label("dist_track_m") == "Distance to track"
    assert feature_label("unknown_thing") == "unknown_thing"
