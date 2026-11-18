import numpy as np

from placement.viewshed import line_of_sight, local_peaks, visibility_matrix

CELL = 30.0
K = 4.0 / 3.0


def test_flat_terrain_is_visible() -> None:
    dem = np.zeros((1, 50))

    assert line_of_sight(dem, CELL, (0, 0), (0, 49), 2.0, 2.0, earth_k=K)


def test_ridge_higher_than_sightline_blocks() -> None:
    dem = np.zeros((1, 50))
    dem[0, 25] = 20.0

    assert not line_of_sight(dem, CELL, (0, 0), (0, 49), 2.0, 10.0, earth_k=K)


def test_ridge_below_sightline_does_not_block() -> None:
    dem = np.zeros((1, 50))
    dem[0, 25] = 5.0

    assert line_of_sight(dem, CELL, (0, 0), (0, 49), 10.0, 10.0, earth_k=K)


def test_earth_curvature_blocks_low_antennas_over_long_flat_path() -> None:
    # 20 km over flat ground: the Earth bulge at mid-path is d1*d2 / (2 k R) ~= 5.9 m.
    dem = np.zeros((1, 668))
    a, b = (0, 0), (0, 667)

    assert not line_of_sight(dem, CELL, a, b, 2.0, 2.0, earth_k=K)
    assert line_of_sight(dem, CELL, a, b, 10.0, 10.0, earth_k=K)


def test_visibility_matrix_respects_terrain_and_range() -> None:
    dem = np.zeros((1, 100))
    dem[0, 50] = 100.0  # a wall in the middle
    gateways = np.array([[0, 0]])
    nodes = np.array([[0, 10], [0, 60], [0, 30]])

    vis = visibility_matrix(
        dem, CELL, gateways, nodes, gateway_h=10.0, node_h=2.0, max_range_m=600.0, earth_k=K
    )

    # node 0: 300 m, clear. node 1: behind the wall. node 2: 900 m, beyond range.
    assert vis.toarray().tolist() == [[True, False, False]]


def test_local_peaks_finds_each_hilltop_once() -> None:
    yy, xx = np.mgrid[0:60, 0:60]
    dem = 100 * np.exp(-((xx - 15) ** 2 + (yy - 15) ** 2) / 50) + 80 * np.exp(
        -((xx - 45) ** 2 + (yy - 40) ** 2) / 50
    )

    rows, cols = local_peaks(dem, window_px=11, min_percentile=50)

    assert sorted(zip(rows.tolist(), cols.tolist(), strict=True)) == [(15, 15), (40, 45)]


def test_local_peaks_ignores_low_ground_and_nan() -> None:
    dem = np.tile(np.linspace(0.0, 40.0, 30), (30, 1))  # ground rising to the east
    dem[5, 5] += 10.0  # a local bump, but low (~17 m) -> below the 99th percentile
    dem[20, 20] = 100.0  # a real summit
    dem[0, 29] = np.nan

    rows, cols = local_peaks(dem, window_px=5, min_percentile=99)

    assert list(zip(rows.tolist(), cols.tolist(), strict=True)) == [(20, 20)]
