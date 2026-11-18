from datetime import UTC, datetime, timedelta

from wamidh_backend.history import thin

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)


def point(i: int, state: str = "NORMAL") -> dict:  # type: ignore[type-arg]
    return {"ts": (T0 + timedelta(seconds=10 * i)).isoformat(), "state": state, "temp_c": 20.0 + i}


def test_short_series_are_returned_unchanged() -> None:
    pts = [point(i) for i in range(5)]

    assert thin(pts, 10) == pts


def test_long_series_are_sampled_evenly_and_keep_both_ends() -> None:
    pts = [point(i) for i in range(1000)]

    out = thin(pts, 100)

    assert len(out) <= 100
    assert out[0] == pts[0] and out[-1] == pts[-1]
    gaps = {int(out[k + 1]["temp_c"] - out[k]["temp_c"]) for k in range(len(out) - 2)}
    assert len(gaps) <= 2  # evenly spaced (rounding allows two step sizes)


def test_every_state_change_survives_thinning() -> None:
    states = ["NORMAL"] * 500 + ["ALERT"] * 3 + ["FIRE"] * 497
    pts = [point(i, s) for i, s in enumerate(states)]

    out = thin(pts, 50)

    kept = [p["state"] for p in out]
    assert "ALERT" in kept and "FIRE" in kept
    # The first ALERT and the first FIRE readings are kept exactly (timeline edges).
    assert pts[500] in out and pts[503] in out
