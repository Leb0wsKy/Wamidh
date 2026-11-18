import itertools

import numpy as np
import pytest
from scipy import sparse

from placement.optimise import (
    coverage_matrix,
    greedy_max_coverage,
    greedy_set_cover,
    random_baseline,
    wind_from_direction,
)


def _cov(rows: list[set[int]], n_targets: int) -> sparse.csr_matrix:
    dense = np.zeros((len(rows), n_targets), dtype=bool)
    for i, cols in enumerate(rows):
        dense[i, list(cols)] = True
    return sparse.csr_matrix(dense)


# --- greedy maximum coverage -------------------------------------------------


def test_greedy_picks_known_optimum_on_toy_grid() -> None:
    # A covers {0,1} (10), B covers {1,2} (6), C covers {3} (4). Optimum for k=2 is {A, C} = 14.
    cov = _cov([{0, 1}, {1, 2}, {3}], n_targets=4)
    risk = np.array([5.0, 5.0, 1.0, 4.0])

    result = greedy_max_coverage(cov, risk, k=2)

    assert result.selected == [0, 2]
    np.testing.assert_allclose(result.cumulative_covered, [10.0, 14.0])


def test_greedy_does_not_count_overlap_twice() -> None:
    # B has the larger raw total (12) but most of it overlaps A; C adds more.
    cov = _cov([{0, 1}, {0, 1, 2}, {3}], n_targets=4)
    risk = np.array([5.0, 5.0, 2.0, 3.0])

    result = greedy_max_coverage(cov, risk, k=2)

    assert result.selected == [1, 2]
    np.testing.assert_allclose(result.cumulative_covered, [12.0, 15.0])


def test_greedy_stops_when_nothing_left_to_cover() -> None:
    cov = _cov([{0}, {0}, {1}], n_targets=2)
    risk = np.array([1.0, 1.0])

    result = greedy_max_coverage(cov, risk, k=10)

    assert len(result.selected) == 2
    assert result.cumulative_covered[-1] == pytest.approx(2.0)


def test_greedy_reaches_one_minus_one_over_e_of_brute_force_optimum() -> None:
    rng = np.random.default_rng(0)
    for _ in range(50):
        n_cand, n_tgt, k = 7, 12, 3
        dense = rng.random((n_cand, n_tgt)) < 0.3
        risk = rng.random(n_tgt)
        best = max(
            risk[dense[list(combo)].any(axis=0)].sum()
            for combo in itertools.combinations(range(n_cand), k)
        )
        got = greedy_max_coverage(sparse.csr_matrix(dense), risk, k=k).cumulative_covered[-1]
        assert got >= (1 - 1 / np.e) * best - 1e-9


# --- coverage matrix ---------------------------------------------------------


def test_coverage_matrix_uses_inclusive_radius() -> None:
    cand = np.array([[0.0, 0.0]])
    targets = np.array([[59.0, 0.0], [0.0, 60.0], [61.0, 0.0]])

    cov = coverage_matrix(cand, targets, radius_m=60.0)

    assert cov.toarray().tolist() == [[True, True, False]]


def test_wind_extends_coverage_upwind_and_shrinks_it_downwind() -> None:
    # Wind FROM the west (270 deg): smoke from a fire west of the node drifts onto it.
    cand = np.array([[0.0, 0.0]])
    targets = np.array(
        [
            [-55.0, 0.0],  # upwind, within full radius -> covered
            [55.0, 0.0],  # downwind, beyond 60 * 0.5 -> not covered
            [25.0, 0.0],  # downwind, within 30 m -> covered
            [0.0, 44.0],  # crosswind, radius 60 * (1 + 0.5) / 2 = 45 -> covered
            [0.0, 46.0],  # crosswind, just outside -> not covered
        ]
    )

    cov = coverage_matrix(cand, targets, radius_m=60.0, wind_from_deg=270.0, downwind_factor=0.5)

    assert cov.toarray().tolist() == [[True, False, True, True, False]]


# --- gateway set cover -------------------------------------------------------


def test_set_cover_finds_minimum_gateways() -> None:
    # G0 sees {0,1,2}, G1 sees {2,3}, G2 sees {3,4}, G3 sees {0,1}. Minimum cover: {G0, G2}.
    vis = _cov([{0, 1, 2}, {2, 3}, {3, 4}, {0, 1}], n_targets=5)

    result = greedy_set_cover(vis)

    assert sorted(result.selected) == [0, 2]
    assert result.uncovered == []


def test_set_cover_reports_nodes_no_gateway_can_see() -> None:
    vis = _cov([{0}, {1}], n_targets=3)

    result = greedy_set_cover(vis)

    assert sorted(result.selected) == [0, 1]
    assert result.uncovered == [2]


# --- wind direction and random baseline ----------------------------------------


@pytest.mark.parametrize(
    ("u", "v", "expected"),
    [
        (1.0, 0.0, 270.0),  # blowing towards the east = wind FROM the west
        (0.0, -1.0, 0.0),  # blowing towards the south = wind FROM the north
        (-1.0, 0.0, 90.0),  # FROM the east
        (1.0, 1.0, 225.0),  # towards the north-east = FROM the south-west
    ],
)
def test_wind_from_direction_uses_meteorological_convention(
    u: float, v: float, expected: float
) -> None:
    assert wind_from_direction(u, v) == pytest.approx(expected)


def test_random_baseline_is_reproducible_and_never_beats_greedy() -> None:
    rng = np.random.default_rng(0)
    cov = sparse.csr_matrix(rng.random((40, 60)) < 0.08)
    risk = rng.random(60)

    base = random_baseline(cov, risk, n=5, repeats=20, seed=1)
    greedy = greedy_max_coverage(cov, risk, k=5).cumulative_covered[-1]

    assert base == random_baseline(cov, risk, n=5, repeats=20, seed=1)
    assert 0 < base["mean"] <= greedy
    assert base["std"] >= 0


# --- minimum spacing between nodes ----------------------------------------------


def test_min_spacing_skips_candidates_next_to_a_chosen_node() -> None:
    # Candidates 0 and 1 sit 100 m apart on the best hotspot; 2 is 5 km away, less risky.
    cov = _cov([{0}, {1}, {2}], n_targets=3)
    risk = np.array([10.0, 9.0, 3.0])
    xy = np.array([[0.0, 0.0], [100.0, 0.0], [5000.0, 0.0]])

    packed = greedy_max_coverage(cov, risk, k=2)
    spaced = greedy_max_coverage(cov, risk, k=2, candidates_xy=xy, min_spacing_m=1000)

    assert packed.selected == [0, 1]
    assert spaced.selected == [0, 2]


def test_min_spacing_stops_when_every_candidate_is_blocked() -> None:
    cov = _cov([{0}, {1}], n_targets=2)
    xy = np.array([[0.0, 0.0], [50.0, 0.0]])

    result = greedy_max_coverage(cov, np.ones(2), k=5, candidates_xy=xy, min_spacing_m=500)

    assert result.selected == [0]
