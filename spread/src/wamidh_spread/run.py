"""One fire: an ensemble of spread scenarios weighted by what the sensors have seen (ADR 0004).

Times inside the model are "fire minutes" since the first detection. In a demo the simulated
fire runs `time_scale` times faster than the clock, so one real second can be one fire minute.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray
from pyproj import Transformer
from scipy.stats import norm

from wamidh_spread.forecast import Forecast, NodeOutlook
from wamidh_spread.landscape import Landscape
from wamidh_spread.physics import Physics, arrival_times

TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
Float = NDArray[np.float64]
VERY_UNLIKELY = -1e3  # log-likelihood for "this scenario cannot explain the observation"


@dataclass(frozen=True)
class Wind:
    from_deg: float  # meteorological: where the wind blows from
    speed_ms: float  # at 10 m
    source: str = "config"


@dataclass(frozen=True)
class NodeRef:
    node_id: int
    lon: float
    lat: float


@dataclass
class _Members:
    wind_from: Float
    wind_ms: Float
    fuel: Float
    ign_x: Float
    ign_y: Float
    ign_cell: NDArray[np.int64]
    lag: Float

    def take(self, idx: NDArray[np.int64]) -> _Members:
        return _Members(*(getattr(self, f)[idx].copy() for f in self.__dataclass_fields__))


@dataclass
class _Stats:
    det: dict[int, Float]  # per sensor: fire minutes from ignition to detection range
    reach: dict[int, Float]  # per sensor: fire minutes from ignition to the sensor itself
    t_ign: Float  # ignition time, fire minutes relative to the first detection
    valid: NDArray[np.bool_]  # the fire can reach the first sensor at all


class SpreadRun:
    def __init__(
        self,
        ls: Landscape,
        phys: Physics,
        cfg: Mapping[str, Any],
        first: NodeRef,
        t0: datetime,
        wind: Wind,
        nodes: Iterable[NodeRef],
        time_scale: float = 1.0,
    ) -> None:
        self.ls, self.phys, self.cfg = ls, phys, cfg
        self.ens = cfg["ensemble"]
        self.sigma = float(cfg["observations"]["sigma_min"])
        self.sigma_rel = float(cfg["observations"].get("sigma_rel", 0.0))
        self.t0, self.wind, self.time_scale = t0, wind, time_scale
        self.first = first
        self.rng = np.random.default_rng(int(self.ens["seed"]))
        self.n = int(self.ens["members"])

        radius = float(cfg["observations"]["detect_radius_m"])
        self.node_xy: dict[int, tuple[float, float]] = {}
        self.node_cells: dict[int, NDArray[np.int64]] = {}
        self.node_cell: dict[int, int] = {}
        for nd in [first, *nodes]:
            x, y = TO_UTM.transform(nd.lon, nd.lat)
            own = ls.cell_of(x, y)
            if own is None:
                continue  # outside the window: the model says nothing about it
            self.node_xy[nd.node_id] = (x, y)
            self.node_cells[nd.node_id] = ls.cells_within(x, y, radius)
            self.node_cell[nd.node_id] = own
        if first.node_id not in self.node_xy:
            raise ValueError(f"sensor {first.node_id} is outside the spread grid")

        self.obs: dict[tuple[int, str], float] = {(first.node_id, "FIRE"): 0.0}
        self.calm: set[int] = set()
        self.now_min = 0.0
        self.m = self._sample_prior()
        self.arrival = self._arrivals(self.m, np.arange(self.n))
        self.st = self._stats(self.arrival, self.m)
        # A scenario whose fire can never reach the first sensor (behind water, say) cannot
        # explain the detection: draw it again.
        for _ in range(5):
            bad = np.flatnonzero(~self.st.valid)
            if bad.size == 0:
                break
            fresh = self._sample_prior()
            for f in self.m.__dataclass_fields__:
                getattr(self.m, f)[bad] = getattr(fresh, f)[bad]
            self.arrival[bad] = self._arrivals(self.m, bad)
            self.st = self._stats(self.arrival, self.m)
        # Members come from the prior: their log-weights start equal and accumulate the
        # likelihood of each detection (the first one is satisfied by construction).
        self.logw = np.where(self.st.valid, 0.0, 2 * VERY_UNLIKELY)
        # Calm-sensor evidence already built into the members (by the last move); a forecast
        # reweights by how it changed since, so it is never counted twice.
        self.calm_ref = np.zeros(self.n)
        self.weights = _normalise(self.logw)
        self.accept_rate = float("nan")

    # --- time ------------------------------------------------------------------------------

    def minutes(self, t: datetime) -> float:
        """Fire minutes since the first detection."""
        return (t - self.t0).total_seconds() / 60 * self.time_scale

    def at(self, fire_min: float) -> datetime:
        return self.t0 + timedelta(minutes=fire_min / self.time_scale)

    # --- members ---------------------------------------------------------------------------

    def _sample_prior(self) -> _Members:
        e, n, rng = self.ens, self.n, self.rng
        wild = rng.random(n) < float(e["wind_dir_outliers"])
        wind_from = (
            np.where(
                wild,
                rng.uniform(0, 360, n),
                self.wind.from_deg + rng.normal(0, float(e["wind_dir_sigma_deg"]), n),
            )
            % 360
        )
        wind_ms = self.wind.speed_ms * np.exp(rng.normal(0, float(e["wind_speed_sigma_log"]), n))
        fuel = np.exp(rng.normal(0, float(e["fuel_sigma_log"]), n))
        # The fire started upwind of the first sensor (its smoke drifted downwind to it),
        # usually close to it (sensors sit where fires start), at most the ignition radius away.
        az = np.radians(wind_from + rng.normal(0, float(e["ignition_upwind_sigma_deg"]), n))
        d = np.minimum(
            np.abs(rng.normal(0, float(e["ignition_distance_sigma_m"]), n)),
            float(e["ignition_radius_m"]),
        )
        fx, fy = self.node_xy[self.first.node_id]
        lo, hi = e["lag_min"]
        m = _Members(
            wind_from=wind_from,
            wind_ms=wind_ms,
            fuel=fuel,
            ign_x=fx + d * np.sin(az),
            ign_y=fy + d * np.cos(az),
            ign_cell=np.zeros(n, dtype=np.int64),
            lag=rng.uniform(float(lo), float(hi), n),
        )
        self._place_ignitions(m, np.arange(n))
        return m

    def _log_prior(self, m: _Members) -> Float:
        """Log density of the prior (up to a constant), for the Metropolis-Hastings moves."""
        e = self.ens
        delta = (m.wind_from - self.wind.from_deg + 180) % 360 - 180
        s_dir = float(e["wind_dir_sigma_deg"])
        out = float(e["wind_dir_outliers"])
        lp = np.log((1 - out) * norm.pdf(delta, 0, s_dir) + out / 360)
        lp += norm.logpdf(
            np.log(m.wind_ms / self.wind.speed_ms), 0, float(e["wind_speed_sigma_log"])
        )
        lp -= np.log(m.wind_ms)
        lp += norm.logpdf(np.log(m.fuel), 0, float(e["fuel_sigma_log"])) - np.log(m.fuel)
        fx, fy = self.node_xy[self.first.node_id]
        dx, dy = m.ign_x - fx, m.ign_y - fy
        az = np.degrees(np.arctan2(dx, dy))
        upwind = (az - m.wind_from + 180) % 360 - 180
        lp += norm.logpdf(upwind, 0, float(e["ignition_upwind_sigma_deg"]))
        # Half-normal distance along a direction: density in the plane ~ pdf(d) / d.
        dist = np.hypot(dx, dy)
        lp += norm.logpdf(dist, 0, float(e["ignition_distance_sigma_m"])) - np.log(
            np.maximum(dist, 50.0)
        )
        lo, hi = e["lag_min"]
        inside = (np.hypot(dx, dy) <= float(e["ignition_radius_m"])) & (m.lag >= lo) & (m.lag <= hi)
        return np.where(inside, lp, -np.inf)

    def _place_ignitions(self, m: _Members, idx: Iterable[int]) -> None:
        """Snap each ignition to its cell; one that does not burn moves to the sensor's cell."""
        fallback = self.node_cell[self.first.node_id]
        ros = self.ls.ros.ravel()
        for i in idx:
            cell = self.ls.cell_of(float(m.ign_x[i]), float(m.ign_y[i]))
            if cell is None or ros[cell] <= 0:
                cell = fallback
                m.ign_x[i], m.ign_y[i] = self.ls.centre_of(cell)
            m.ign_cell[i] = cell

    def _arrivals(self, m: _Members, idx: NDArray[np.int64]) -> NDArray[np.float32]:
        out = np.empty((idx.size, self.ls.size), dtype=np.float32)
        for k, i in enumerate(idx):
            out[k] = arrival_times(
                self.ls,
                int(m.ign_cell[i]),
                self.phys,
                float(m.wind_from[i]),
                float(m.wind_ms[i]),
                float(m.fuel[i]),
            )
        return out

    def _stats(self, arrival: NDArray[np.float32], m: _Members) -> _Stats:
        """Per member: when each sensor would detect the fire, and the ignition time."""
        det = {nid: arrival[:, c].min(axis=1).astype(float) for nid, c in self.node_cells.items()}
        reach = {nid: arrival[:, c].astype(float) for nid, c in self.node_cell.items()}
        # The first sensor detected at fire minute 0: the ignition was that long before.
        t_ign = -(det[self.first.node_id] + m.lag)
        valid = np.isfinite(t_ign)
        return _Stats(det, reach, np.where(valid, t_ign, 0.0), valid)

    @property
    def t_ign(self) -> Float:
        return self.st.t_ign

    @property
    def det(self) -> dict[int, Float]:
        return self.st.det

    # --- the filter ------------------------------------------------------------------------

    def observe(self, node_id: int, event: str, t: datetime) -> None:
        """A sensor reported FIRE, or went silent in the fire (LOST)."""
        if node_id not in self.node_xy or (node_id, event) in self.obs:
            return
        t_min = self.minutes(t)
        self.obs[(node_id, event)] = t_min
        self.now_min = max(self.now_min, t_min)
        self.calm.discard(node_id)
        self.logw = self.logw + self._obs_ll(self.st, self.m, {(node_id, event): t_min})
        self._update_weights(allow_move=True)

    def _update_weights(self, allow_move: bool) -> None:
        self.weights = _normalise(self.logw + self._calm_ll(self.st, self.m) - self.calm_ref)
        if allow_move and self.ess_ratio < float(self.ens["resample_below_ess"]):
            self._resample_move()

    def _obs_ll(self, st: _Stats, m: _Members, obs: Mapping[tuple[int, str], float]) -> Float:
        """Log-likelihood of detections (FIRE) and sensors lost in the fire (LOST)."""
        ll = np.zeros(t_len := st.t_ign.size)
        for (nid, kind), t in obs.items():
            s = self._sigma(t)
            if kind == "FIRE":
                pred = st.t_ign + st.det[nid] + m.lag
                term = -0.5 * ((t - pred) / s) ** 2
            else:  # LOST: the fire had reached the sensor itself by then
                term = norm.logcdf((t - (st.t_ign + st.reach[nid])) / s)
            ll += np.where(np.isfinite(term), term, VERY_UNLIKELY)
        return np.where(st.valid, ll, np.full(t_len, 2 * VERY_UNLIKELY))

    def _calm_ll(self, st: _Stats, m: _Members) -> Float:
        """Negative evidence: each sensor still calm now must not have been reached already."""
        ll = np.zeros(st.t_ign.size)
        seen = {nid for nid, _ in self.obs}
        for nid in self.calm - seen:
            if nid in st.det:
                pred = st.t_ign + st.det[nid] + m.lag
                s = self._sigma(self.now_min)
                term = np.where(np.isfinite(pred), norm.logsf((self.now_min - pred) / s), 0.0)
                ll += np.maximum(term, VERY_UNLIKELY)
        return ll

    def _sigma(self, t: float) -> float:
        """Timing error of the model: a few minutes at first, growing with the time since the
        first detection (an error on the rate of spread is an error proportional to time)."""
        return math.hypot(self.sigma, self.sigma_rel * max(t, 0.0))

    @property
    def ess_ratio(self) -> float:
        return float(1 / np.sum(self.weights**2) / self.n)

    def _resample_move(self) -> None:
        """Resample by weight, then move every member with Metropolis-Hastings steps whose
        target is prior x likelihood of all detections (Gilks & Berzuini 2001). The ensemble
        follows the evidence without piling onto one scenario or drifting to implausible
        winds."""
        n = self.n
        positions = (self.rng.random() + np.arange(n)) / n
        parents = np.minimum(np.searchsorted(np.cumsum(self.weights), positions), n - 1)
        self.m = self.m.take(parents)
        self.arrival = self.arrival[parents]
        self.st = self._stats(self.arrival, self.m)

        def log_target(st: _Stats, m: _Members) -> Float:
            return self._log_prior(m) + self._obs_ll(st, m, self.obs) + self._calm_ll(st, m)

        target = log_target(self.st, self.m)
        for _ in range(int(self.ens.get("move_rounds", 1))):
            proposal = self._jitter(self.m)
            idx = np.arange(n)
            arrival = self._arrivals(proposal, idx)
            st = self._stats(arrival, proposal)
            new_target = log_target(st, proposal)
            with np.errstate(invalid="ignore"):
                accept = np.log(self.rng.random(n)) < (new_target - target)
            for f in self.m.__dataclass_fields__:
                getattr(self.m, f)[accept] = getattr(proposal, f)[accept]
            self.arrival[accept] = arrival[accept]
            target = np.where(accept, new_target, target)
            self.st = self._stats(self.arrival, self.m)
            self.accept_rate = float(accept.mean())
        self.logw = np.zeros(n)  # equally weighted posterior sample
        self.calm_ref = self._calm_ll(self.st, self.m)
        self.weights = _normalise(self.logw)

    def _jitter(self, m: _Members) -> _Members:
        """Random-walk proposal; steps scale with the current spread of the members (half of
        it), never below the configured jitter."""
        j, n, rng = self.ens["jitter"], self.n, self.rng

        def half_std(v: Float) -> float:
            return 0.5 * float(np.std(v))

        rel = (m.wind_from - _circular_mean(m.wind_from, np.full(n, 1 / n)) + 180) % 360 - 180
        p = m.take(np.arange(n))
        p.wind_from = (p.wind_from + rng.normal(0, max(j["wind_dir_deg"], half_std(rel)), n)) % 360
        p.wind_ms = p.wind_ms * np.exp(
            rng.normal(0, max(j["wind_speed_rel"], half_std(np.log(m.wind_ms))), n)
        )
        p.fuel = p.fuel * np.exp(rng.normal(0, max(j["fuel_rel"], half_std(np.log(m.fuel))), n))
        s_ign = max(j["ignition_m"], half_std(m.ign_x), half_std(m.ign_y))
        p.ign_x = p.ign_x + rng.normal(0, s_ign, n)
        p.ign_y = p.ign_y + rng.normal(0, s_ign, n)
        p.lag = p.lag + rng.normal(0, max(j["lag_min"], half_std(m.lag)), n)
        self._place_ignitions(p, np.arange(n))
        return p

    # --- forecast --------------------------------------------------------------------------

    def forecast(self, now: datetime, calm: set[int]) -> Forecast:
        """The outlook at `now`, given the sensors still calm (NORMAL) at that moment."""
        self.now_min = max(self.now_min, self.minutes(now))
        self.calm = {c for c in calm if c in self.node_xy}
        self._update_weights(allow_move=True)
        horizons = [0, *map(int, self.cfg["forecast"]["horizons_min"])]
        burn = self.t_ign[:, None] + self.arrival  # absolute fire minute each cell burns
        prob = {h: self.weights @ (burn <= self.now_min + h) for h in horizons}

        heading, speed = self._head(burn, self.now_min + 60)
        w = self.weights
        ix, iy = float(w @ self.m.ign_x), float(w @ self.m.ign_y)
        spread_m = math.sqrt(float(w @ ((self.m.ign_x - ix) ** 2 + (self.m.ign_y - iy) ** 2)))
        return Forecast(
            landscape=self.ls,
            computed_at=now,
            fire_minutes=self.now_min,
            time_scale=self.time_scale,
            probabilities=prob,
            bands=[float(b) for b in self.cfg["forecast"]["bands"]],
            simplify_m=float(self.cfg["forecast"]["simplify_m"]),
            ignition_xy=(ix, iy),
            ignition_uncertainty_m=spread_m,
            ignition_at=self.at(float(w @ self.t_ign)),
            heading_deg=heading,
            speed_m_min=speed,
            wind_from_deg=_circular_mean(self.m.wind_from, w),
            wind_ms=float(w @ self.m.wind_ms),
            wind_observed=self.wind,
            members=self.n,
            ess_ratio=self.ess_ratio,
            observed=sorted(
                ((nid, kind, self.at(t)) for (nid, kind), t in self.obs.items()),
                key=lambda o: o[2],
            ),
            next_nodes=self._next_nodes(),
        )

    def _head(self, burn: Float, until: float) -> tuple[float, float]:
        """Direction and speed of the head: per member, the burned cell farthest from its
        ignition by `until`, averaged over members by weight."""
        xs, ys = self.ls.centres()
        dx = xs[None, :] - self.m.ign_x[:, None]
        dy = ys[None, :] - self.m.ign_y[:, None]
        dist = np.where(burn <= until, np.hypot(dx, dy), -1.0)
        far = dist.argmax(axis=1)
        rows = np.arange(self.n)
        reach = np.maximum(dist[rows, far], 0.0)
        bearing = (np.degrees(np.arctan2(dx[rows, far], dy[rows, far])) + 360) % 360
        elapsed = np.maximum(until - self.t_ign, 1e-6)
        moving = reach > 0
        w = self.weights * moving
        if w.sum() == 0:
            return float("nan"), 0.0
        w = w / w.sum()
        return _circular_mean(bearing, w), float(w @ (reach / elapsed))

    def _next_nodes(self, limit: int = 6) -> list[NodeOutlook]:
        """Sensors not reached yet, by expected detection time."""
        seen = {nid for nid, _ in self.obs}
        out = []
        for nid, det in self.det.items():
            if nid in seen:
                continue
            pred = self.t_ign + det + self.m.lag - self.now_min  # minutes from now
            p60 = float(self.weights @ (pred <= 60))
            p120 = float(self.weights @ (pred <= 120))
            if p120 < 0.05:
                continue
            finite = np.isfinite(pred)
            order = np.argsort(np.where(finite, pred, np.inf))
            cum = np.cumsum(self.weights[order])
            median = pred[order][min(int(np.searchsorted(cum, 0.5)), self.n - 1)]
            eta = float(max(median, 0.0)) if np.isfinite(median) else float("inf")
            out.append(NodeOutlook(nid, p60, p120, eta))
        return sorted(out, key=lambda o: (o.eta_min, -o.p_within_60))[:limit]


def _normalise(logw: Float) -> Float:
    w = np.exp(logw - logw.max())
    return np.asarray(w / w.sum(), dtype=np.float64)


def _circular_mean(deg: Float, w: Float) -> float:
    r = np.radians(deg)
    return float((np.degrees(np.arctan2(w @ np.sin(r), w @ np.cos(r))) + 360) % 360)
