import numpy as np
from rasterio.transform import Affine

from placement.grid import Grid, aggregate_mean


def test_grid_covering_snaps_outward_to_cell_multiples() -> None:
    g = Grid.covering(xmin=100, ymin=200, xmax=900, ymax=1000, cell=375)

    assert (g.x0, g.y0, g.ncols, g.nrows) == (0, 1125, 3, 3)


def test_grid_index_and_centres_round_trip() -> None:
    g = Grid(x0=0, y0=1125, cell=375, nrows=3, ncols=3)

    rows, cols = g.index(np.array([10.0, 400.0, 2000.0]), np.array([1120.0, 700.0, 100.0]))

    assert rows.tolist() == [0, 1, -1]
    assert cols.tolist() == [0, 1, -1]
    xc, yc = g.centres(np.array([1]), np.array([2]))
    assert (xc[0], yc[0]) == (937.5, 562.5)


def test_aggregate_mean_averages_pixels_by_centre_and_ignores_nan() -> None:
    # 4x4 raster of 100 m pixels, top-left at (0, 400); grid of 200 m cells -> 2x2.
    raster = np.array(
        [
            [1, 3, 10, 10],
            [5, 7, 10, np.nan],
            [0, 0, np.nan, np.nan],
            [0, 4, np.nan, np.nan],
        ],
        dtype=float,
    )
    transform = Affine(100, 0, 0, 0, -100, 400)
    g = Grid(x0=0, y0=400, cell=200, nrows=2, ncols=2)

    out = aggregate_mean(raster, transform, g)

    np.testing.assert_allclose(out, [[4.0, 10.0], [1.0, np.nan]])


def test_to_raster_places_values_and_leaves_nan_elsewhere() -> None:
    g = Grid(x0=0, y0=300, cell=100, nrows=3, ncols=3)

    r = g.to_raster(np.array([0, 2]), np.array([1, 2]), np.array([0.5, 0.9]))

    assert r.shape == (3, 3)
    assert r[0, 1] == 0.5 and r[2, 2] == 0.9
    assert np.isnan(r).sum() == 7


def test_window_cuts_a_sub_grid_covering_a_box() -> None:
    g = Grid(x0=0, y0=1000, cell=100, nrows=10, ncols=10)

    (r0, r1, c0, c1), sub = g.window(xmin=250, ymin=420, xmax=480, ymax=710)

    assert (r0, r1, c0, c1) == (2, 6, 2, 5)
    assert (sub.x0, sub.y0, sub.nrows, sub.ncols) == (200, 800, 4, 3)
