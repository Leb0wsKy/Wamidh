"""Helpers for the NASA FIRMS area API."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, timedelta


class FirmsError(RuntimeError):
    pass


def fetch_with_backoff(
    url: str,
    get: Callable[[str], tuple[int, str]],
    sleep: Callable[[float], None],
    wait_s: float,
    max_tries: int = 20,
) -> str:
    """GET a FIRMS CSV, waiting `wait_s` and retrying while the MAP_KEY quota is exhausted.

    The quota is 5000 transactions per 10 minutes, and a large bbox costs several
    transactions per request, so long downloads hit it. Any other error raises at once.
    """
    for _ in range(max_tries):
        status, text = get(url)
        if "transaction limit" in text.lower():
            sleep(wait_s)
            continue
        if status != 200 or text.lstrip().lower().startswith(("invalid", "error")):
            raise FirmsError(f"FIRMS request failed ({status}): {text[:200]}")
        return text
    raise FirmsError(f"FIRMS transaction limit still exceeded after {max_tries} tries")


def request_windows(
    start_year: int, end_year: int, months: Iterable[int], day_range: int
) -> list[tuple[date, int]]:
    """Split the fire season of each year into (start_date, n_days) API requests.

    Every in-season day is requested exactly once; no window crosses into an
    out-of-season month or exceeds `day_range` days.
    """
    months = set(months)
    windows: list[tuple[date, int]] = []
    for year in range(start_year, end_year + 1):
        day = date(year, 1, 1)
        run: list[date] = []
        while day.year == year:
            if day.month in months:
                run.append(day)
            if run and (day.month not in months or len(run) == day_range):
                windows.append((run[0], len(run)))
                run = []
            day += timedelta(days=1)
        if run:
            windows.append((run[0], len(run)))
    return windows
