import numpy as np
from rasterio.transform import Affine
from shapely.geometry import LineString, Point

from placement.features import (
    count_within,
    distance_to_lines,
    distance_to_mask,
    distance_to_points,
    fill_nan_nearest,
    sample_raster,
    window_mean,
)

T100 = Affine(100, 0, 0, 0, -100, 400)  # 100 m pixels, top-left (0, 400)


def test_distance_to_lines_is_exact_perpendicular_distance() -> None:
    lines = [LineString([(0, 0), (1000, 0)]), LineString([(0, 500), (0, 900)])]

    d = distance_to_lines(np.array([500.0, 30.0, 1300.0]), np.array([40.0, 700.0, 400.0]), lines)

    np.testing.assert_allclose(d, [40.0, 30.0, 500.0])


def test_distance_to_points() -> None:
    d = distance_to_points(np.array([0.0, 30.0]), np.array([0.0, 40.0]), [Point(0, 0)])

    np.testing.assert_allclose(d, [0.0, 50.0])


def test_distance_to_mask_in_metres() -> None:
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, 0] = True

    d = distance_to_mask(mask, pixel_m=100.0)

    assert d[0, 0] == 0.0
    assert d[0, 3] == 300.0
    np.testing.assert_allclose(d[3, 3], np.hypot(300, 300))


def test_sample_raster_nearest_pixel_and_nan_outside() -> None:
    raster = np.arange(16, dtype=float).reshape(4, 4)

    v = sample_raster(raster, T100, np.array([150.0, 399.0, 500.0]), np.array([350.0, 1.0, 100.0]))

    np.testing.assert_allclose(v, [1.0, 15.0, np.nan])


def test_fill_nan_nearest_uses_closest_valid_pixel() -> None:
    raster = np.array([[1.0, np.nan, np.nan, 9.0]])

    np.testing.assert_allclose(fill_nan_nearest(raster), [[1.0, 1.0, 9.0, 9.0]])


def test_window_mean_averages_a_square_footprint() -> None:
    raster = np.zeros((4, 4))
    raster[:2, :2] = 1.0  # top-left 200 x 200 m block

    # 200 m footprint centred on (100, 300) covers exactly the block; at (300, 100) none of it.
    v = window_mean(raster, T100, np.array([100.0, 300.0]), np.array([300.0, 100.0]), half_m=100)

    np.testing.assert_allclose(v, [1.0, 0.0])


def test_count_within_radius_includes_the_boundary() -> None:
    px = np.array([0.0, 1000.0, 3000.0])
    py = np.zeros(3)

    counts = count_within(np.array([0.0, 2000.0]), np.array([0.0, 0.0]), px, py, radius_m=1000)

    assert counts.tolist() == [2, 2]  # (0,0) sees 0 and 1000; (2000,0) sees 1000 and 3000


def test_count_within_with_no_points_is_zero() -> None:
    counts = count_within(np.array([0.0]), np.array([0.0]), np.array([]), np.array([]), 500)

    assert counts.tolist() == [0]
