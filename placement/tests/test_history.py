import numpy as np
import pandas as pd

from placement.history import HistoryWindows, history_features, in_window, rank_normalise


def test_windows_have_equal_length_for_training_and_deployment() -> None:
    w = HistoryWindows.from_years(first_year=2001, history_end_year=2016, last_year=2025)

    assert (w.train_start, w.train_end) == (2001, 2016)
    assert (w.target_start, w.target_end) == (2017, 2025)
    assert (w.deploy_start, w.deploy_end) == (2010, 2025)  # same 16-year length


def test_in_window_selects_by_year() -> None:
    df = pd.DataFrame(
        {"time": pd.to_datetime(["2009-07-01", "2010-07-01", "2016-08-01"], utc=True)}
    )

    assert in_window(df, 2010, 2016).tolist() == [False, True, True]


def test_history_features_count_nearby_past_fires() -> None:
    cells = pd.DataFrame({"cell_id": [1, 2], "x": [0.0, 10_000.0], "y": [0.0, 0.0]})
    ign = pd.DataFrame({"x": [500.0, 3000.0], "y": [0.0, 0.0]})
    det = pd.DataFrame({"x": [0.0, 100.0, 9000.0], "y": [0.0, 0.0, 0.0]})

    f = history_features(cells, ign, det, radii_m=[1000, 5000])

    assert f.hist_ign_1km.tolist() == [1, 0]
    assert f.hist_ign_5km.tolist() == [2, 0]
    assert f.hist_det_1km.tolist() == [2, 1]
    np.testing.assert_allclose(f.dist_hist_ign_m, [500.0, 7000.0])


def test_rank_normalise_removes_a_level_shift_between_windows() -> None:
    train = pd.DataFrame({"cell_id": [1, 2, 3, 4], "n_fires": [0, 1, 2, 4]})
    deploy = train.assign(n_fires=train.n_fires * 2 + 1)  # same ordering, doubled level

    a = rank_normalise(train, ["n_fires"])
    b = rank_normalise(deploy, ["n_fires"])

    np.testing.assert_allclose(a.n_fires, b.n_fires)
    np.testing.assert_allclose(a.n_fires, [0.0, 1 / 3, 2 / 3, 1.0])
    assert a.cell_id.tolist() == [1, 2, 3, 4]


def test_rank_normalise_gives_ties_the_same_value() -> None:
    df = pd.DataFrame({"cell_id": [1, 2, 3], "n_fires": [0, 0, 5]})

    out = rank_normalise(df, ["n_fires"])

    assert out.n_fires[0] == out.n_fires[1] < out.n_fires[2]
