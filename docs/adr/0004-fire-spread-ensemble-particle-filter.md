# ADR 0004: fire spread prediction by a physics ensemble corrected by sensor alerts

- **Status:** accepted, 2026-10-06
- **Scope:** `spread/` (engine), `backend/` (weather + spread service, `/incidents/{id}/forecast`),
  `simulator/` (closed-loop fires), `web/` (Propagation tab)

## Context

Once a fire is detected, crews need to know where it is heading and what it will reach in the
next hours. The network gives a strong, unusual signal: the **order and timing in which sensors
detect the fire** (a second detection east of the first means the fire runs east), and the
sensors still calm say where it has **not** arrived yet. Wind is the other main driver.

No dataset pairs sensor alerts with fire progressions, so a model trained end to end would learn
only from fires we simulate ourselves: a black box trained on our own assumptions.

## Decision

- **Physics model.** Arrival time over a 100 m grid around the first detecting sensor, by
  minimum travel time on a 16-neighbour grid (Finney 2002; 16 neighbours reduce the diamond
  artefacts of 8). Each edge's rate of spread combines:
  - a base rate per fuel class from ESA WorldCover, modulated by summer NDVI
    (`spread/config/fuels.yaml`, every value an ASSUMPTION from the literature);
  - slope: x exp(0.069 * slope°) along the direction of travel (about x2 per 10° upslope);
  - wind: head rate x exp(0.05039 * U10 km/h) (Canadian FBP System ISI wind function, Van
    Wagner 1987) and an elliptical shape whose length-to-breadth ratio follows Anderson (1983).
- **Ensemble.** 200 members differ in wind direction and speed (around the observed wind, with
  a few wide outliers), a fuel-rate multiplier, the ignition point (upwind of the first sensor,
  within its detection radius) and the detection lag.
- **Particle filter (the learning part).** Each member's weight is the likelihood of everything
  the network has seen: when each sensor detected the fire, which sensors were lost in it, and
  which sensors are still calm (negative evidence). When the weights collapse, members are
  regenerated around the plausible ones. Weights are recomputed from all observations at each
  update, so repeated calm reports are never counted twice.
- **Output.** Probability that each cell burns within 15 / 30 / 60 / 120 min (contours at 20,
  50 and 80 %), the estimated ignition point and time, heading and speed of the head, threatened
  population zones, and the effective number of plausible members (confidence).
- **Wind** comes from OpenWeatherMap (key in `.env`), cached 10 min, falling back to the last
  value received, then to a configured default. The source is always shown.
- **Advisory.** The forecast supports decisions; it never triggers anything by itself.

## Limits, stated honestly

- Measured on synthetic fires and one live closed-loop run (`spread/README.md`): the heading and
  wind direction are recovered within a few degrees after two or three detections. When a fire
  starts midway between sensors, the first detections can fit several fires and the forecast
  stays wide until more sensors report.
- With few detections a fast fire can be explained by strong wind or by flammable fuel; the
  model tends to underestimate wind speed and compensate with fuel.
- Fuel rates and the wind and slope factors are literature values, not calibrated on Tunisian
  fires. The backtest on documented fires (Melloula, July 2023) is still to do.
- Wind is uniform over the window and constant in time; gusts, spotting and night-time slowdown
  are not modelled.
- The demo runs fires 60x faster than real time; the backend is told so by configuration
  (`spread.time_scale`), and the interface says so.

## Alternatives considered

- **A trained neural network:** no real training data; it would only re-learn our simulator.
- **A cellular automaton with fixed probabilities:** cheaper but not physically interpretable,
  and its spread speed depends on the grid.
- **FARSITE / Prometheus:** full simulators, heavy to install and too slow for an ensemble of
  200 updated every few seconds on one laptop.
