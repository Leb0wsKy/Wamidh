from datetime import date, timedelta

import pytest

from placement.firms import FirmsError, fetch_with_backoff, request_windows

LIMIT = (400, "Exceeding allowed transaction limit.")
CSV = (200, "latitude,longitude\n36.8,8.7\n")


def _scripted(responses: list[tuple[int, str]]):  # type: ignore[no-untyped-def]
    calls = iter(responses)
    return lambda url: next(calls)


def test_fetch_waits_and_retries_when_transaction_limit_is_hit() -> None:
    slept: list[float] = []

    text = fetch_with_backoff(
        "u", _scripted([LIMIT, LIMIT, CSV]), sleep=slept.append, wait_s=60, max_tries=5
    )

    assert text == CSV[1]
    assert slept == [60, 60]


def test_fetch_gives_up_after_max_tries() -> None:
    with pytest.raises(FirmsError, match="transaction limit"):
        fetch_with_backoff("u", _scripted([LIMIT] * 3), sleep=lambda s: None, wait_s=1, max_tries=3)


def test_fetch_raises_immediately_on_other_errors() -> None:
    with pytest.raises(FirmsError, match="Invalid MAP_KEY"):
        fetch_with_backoff(
            "u", _scripted([(400, "Invalid MAP_KEY."), CSV]), sleep=lambda s: None, wait_s=1
        )


def test_windows_cover_each_season_day_exactly_once() -> None:
    windows = request_windows(2020, 2021, months=[5, 6, 7, 8, 9, 10], day_range=5)

    days = [start + timedelta(days=i) for start, n in windows for i in range(n)]
    assert len(days) == len(set(days)) == 2 * 184
    assert min(days) == date(2020, 5, 1)
    assert max(days) == date(2021, 10, 31)
    assert all(d.month in range(5, 11) for d in days)


def test_windows_never_exceed_api_day_range() -> None:
    windows = request_windows(2019, 2019, months=[7], day_range=5)

    assert all(1 <= n <= 5 for _, n in windows)
    assert windows[-1] == (date(2019, 7, 31), 1)
