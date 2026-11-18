"""Wind at a fire, from OpenWeatherMap (ADR 0004).

The key comes from OPENWEATHER_API_KEY (environment or the repo's .env) and is never logged.
Readings are cached; without network the last value received is used, then a configured
default, and the source always says which.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger("wamidh.weather")
OWM_URL = "https://api.openweathermap.org/data/2.5/weather"


@dataclass(frozen=True)
class WindReading:
    from_deg: float  # meteorological: where the wind blows from
    speed_ms: float  # at 10 m
    source: str
    observed_at: datetime

    def to_json(self) -> dict[str, Any]:
        return {
            "from_deg": round(self.from_deg, 1),
            "speed_ms": round(self.speed_ms, 1),
            "source": self.source,
            "observed_at": self.observed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }


class WindProvider(Protocol):
    def wind(self, lat: float, lon: float) -> tuple[float, float]:
        """(from_deg, speed_ms) now at that point; raises OSError when unreachable."""
        ...


def _fetch_json(url: str, timeout_s: float = 4.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout_s) as res:
        data: dict[str, Any] = json.loads(res.read())
        return data


class OpenWeatherMap:
    """Current weather API (free tier): wind speed in m/s and direction in degrees."""

    def __init__(
        self,
        key: str,
        fetch: Callable[[str], dict[str, Any]] | None = None,
        timeout_s: float = 4.0,
    ) -> None:
        self._key = key
        self._fetch = fetch or (lambda url: _fetch_json(url, timeout_s))

    def __repr__(self) -> str:
        return "OpenWeatherMap(key=***)"

    def wind(self, lat: float, lon: float) -> tuple[float, float]:
        query = urllib.parse.urlencode(
            {"lat": round(lat, 4), "lon": round(lon, 4), "appid": self._key, "units": "metric"}
        )
        try:
            data = self._fetch(f"{OWM_URL}?{query}")
        except Exception as e:  # urllib errors carry the URL, and so the key
            raise OSError(str(e).replace(self._key, "***")) from None
        w = data["wind"]
        return float(w.get("deg", 0.0)), float(w["speed"])


class WeatherService:
    def __init__(
        self,
        provider: WindProvider | None,
        cache_s: float,
        default: Mapping[str, float],
        override: Mapping[str, float] | None = None,
    ) -> None:
        self.provider = provider
        # DEMO ONLY: a fixed wind in place of the measurement, so a simulated fire and the
        # forecast share the same weather on a calm day. Always reported as "demo".
        self.override = override
        self.cache = timedelta(seconds=cache_s)
        self.default = default
        self._last: WindReading | None = None

    def wind(self, lat: float, lon: float, now: datetime) -> WindReading:
        if self.override:
            return WindReading(
                float(self.override["from_deg"]) % 360,
                float(self.override["speed_ms"]),
                "demo",
                now,
            )
        if self.provider is None:
            return self._fallback(now, "default (no API key)")
        if self._last and now - self._last.observed_at < self.cache:
            return self._last
        try:
            from_deg, speed = self.provider.wind(lat, lon)
        except (OSError, KeyError, ValueError) as e:
            log.warning("wind: OpenWeatherMap unreachable (%s)", e)
            if self._last:
                return WindReading(
                    self._last.from_deg,
                    self._last.speed_ms,
                    "openweathermap (last known)",
                    self._last.observed_at,
                )
            return self._fallback(now, "default (offline)")
        self._last = WindReading(from_deg % 360, speed, "openweathermap", now)
        return self._last

    def _fallback(self, now: datetime, source: str) -> WindReading:
        return WindReading(
            float(self.default["from_deg"]), float(self.default["speed_ms"]), source, now
        )


def read_secret(name: str, repo: Path, env: Mapping[str, str]) -> str | None:
    """A secret from the environment, else from the repo's .env file; None if absent."""
    if env.get(name, "").strip():
        return env[name].strip()
    path = repo / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name and value.strip():
                return value.strip()
    return None
