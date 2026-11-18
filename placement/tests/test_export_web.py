import numpy as np
from shapely.geometry import LineString

from placement.export_web import colorize_percentile, nearest_access


def test_colorize_makes_nan_transparent_and_high_risk_darker() -> None:
    pct = np.array([[0.0, 50.0], [100.0, np.nan]])

    rgba = colorize_percentile(pct, alpha=200)

    assert rgba.shape == (2, 2, 4) and rgba.dtype == np.uint8
    assert rgba[1, 1, 3] == 0  # not modelled -> transparent
    assert rgba[0, 0, 3] == rgba[1, 0, 3] == 200
    luminance = rgba[..., :3].astype(float) @ np.array([0.2126, 0.7152, 0.0722])
    assert luminance[0, 0] > luminance[0, 1] > luminance[1, 0]  # darker = riskier


def test_nearest_access_snaps_each_point_to_the_closest_line() -> None:
    lines = [LineString([(0, 0), (100, 0)]), LineString([(0, 50), (0, 100)])]
    kinds = ["track", "residential"]

    xs, ys, found = nearest_access(np.array([40.0, 10.0]), np.array([30.0, 80.0]), lines, kinds)

    np.testing.assert_allclose(xs, [40.0, 0.0])
    np.testing.assert_allclose(ys, [0.0, 80.0])
    assert found == ["track", "residential"]
