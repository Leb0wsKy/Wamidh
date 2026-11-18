from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from wamidh_backend.weather import OpenWeatherMap, WeatherService, read_secret

T0 = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
DEFAULT = {"from_deg": 270.0, "speed_ms": 5.0}


class FakeOwm:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.calls = 0

    def wind(self, lat: float, lon: float) -> tuple[float, float]:
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply  # type: ignore[no-any-return]


def test_live_wind_is_cached_for_ten_minutes() -> None:
    owm = FakeOwm([(250.0, 7.5), (260.0, 8.0)])
    svc = WeatherService(owm, cache_s=600, default=DEFAULT)

    first = svc.wind(36.8, 8.7, T0)
    again = svc.wind(36.8, 8.7, T0 + timedelta(minutes=5))
    later = svc.wind(36.8, 8.7, T0 + timedelta(minutes=11))

    assert (first.from_deg, first.speed_ms, first.source) == (250.0, 7.5, "openweathermap")
    assert again == first and owm.calls == 2
    assert later.from_deg == 260.0


def test_offline_falls_back_to_the_last_value_then_to_the_default() -> None:
    owm = FakeOwm([(250.0, 7.5), OSError("no network"), OSError("no network")])
    svc = WeatherService(owm, cache_s=60, default=DEFAULT)
    svc.wind(36.8, 8.7, T0)

    stale = svc.wind(36.8, 8.7, T0 + timedelta(minutes=5))
    assert (stale.from_deg, stale.source) == (250.0, "openweathermap (last known)")

    cold = WeatherService(FakeOwm([OSError("no network")]), cache_s=60, default=DEFAULT)
    assert cold.wind(36.8, 8.7, T0).source == "default (offline)"


def test_without_a_key_the_default_wind_is_used() -> None:
    svc = WeatherService(None, cache_s=600, default=DEFAULT)

    w = svc.wind(36.8, 8.7, T0)

    assert (w.from_deg, w.speed_ms, w.source) == (270.0, 5.0, "default (no API key)")


def test_openweathermap_reply_is_parsed_and_the_key_never_leaks() -> None:
    seen: list[str] = []

    def fetch(url: str) -> dict[str, Any]:
        seen.append(url)
        return {"wind": {"speed": 6.2, "deg": 285}, "dt": 1784556000}

    owm = OpenWeatherMap("secret-key", fetch=fetch)

    assert owm.wind(36.8, 8.7) == (285.0, 6.2)
    assert "lat=36.8" in seen[0] and "appid=secret-key" in seen[0]
    assert "secret-key" not in repr(owm)


def test_openweathermap_error_does_not_show_the_key() -> None:
    def fetch(url: str) -> dict[str, Any]:
        raise OSError(f"HTTP 401 for {url}")

    with pytest.raises(OSError) as err:
        OpenWeatherMap("secret-key", fetch=fetch).wind(36.8, 8.7)
    assert "secret-key" not in str(err.value)


def test_secret_comes_from_the_environment_or_the_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OTHER=1\nOPENWEATHER_API_KEY= abc123 \n", encoding="utf-8")

    assert read_secret("OPENWEATHER_API_KEY", tmp_path, {}) == "abc123"
    assert read_secret("OPENWEATHER_API_KEY", tmp_path, {"OPENWEATHER_API_KEY": "env"}) == "env"
    assert read_secret("MISSING", tmp_path, {}) is None


def test_a_demo_wind_overrides_the_measurement_and_says_so() -> None:
    owm = FakeOwm([(250.0, 7.5)])
    svc = WeatherService(
        owm, cache_s=600, default=DEFAULT, override={"from_deg": 210, "speed_ms": 8}
    )

    w = svc.wind(36.8, 8.7, T0)

    assert (w.from_deg, w.speed_ms, w.source) == (210.0, 8.0, "demo")
    assert owm.calls == 0
