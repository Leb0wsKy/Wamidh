# spread/ — fire spread prediction engine

Predicts where a detected fire will be within the next 15, 30, 60 and 120 minutes. A physics
model is run as an ensemble, and the ensemble is corrected by what the sensors report
([ADR 0004](../docs/adr/0004-fire-spread-ensemble-particle-filter.md)). The backend imports it
in-process; the Propagation tab shows the result.

```python
from wamidh_spread.engine import SpreadEngine
from wamidh_spread.run import NodeRef, Wind

engine = SpreadEngine.from_config("spread/config/kroumirie.yaml")
run = engine.start(first=NodeRef(13, lon, lat), t0=detected_at, wind=Wind(210, 8, "openweathermap"),
                   nodes=all_sensors, time_scale=1)
run.observe(56, "FIRE", t)          # another sensor detects the fire
run.observe(13, "LOST", t)          # a sensor went silent in the fire
forecast = run.forecast(now, calm={...}).to_json()   # sensors still NORMAL = negative evidence
```

## How it works

1. **Ground.** A 12 × 12 km window at 100 m around the first sensor, cut from the pilot-zone
   rasters: elevation (slope and aspect recomputed at 100 m), ESA WorldCover fuel classes and
   summer NDVI. Base rates per fuel class: `config/fuels.yaml`, all `ASSUMPTION`.
2. **Physics.** Minimum travel time on a 16-neighbour grid (Finney 2002), with SciPy's
   Dijkstra. Each edge's rate combines:
   - the fuel rate, ×exp(0.069·slope°) uphill;
   - wind, as the FBP ISI function with its rate curvature (`wind_exponent`);
   - an Anderson (1983) ellipse.
   Knight moves never jump a non-burnable cell.
3. **Ensemble.** 200 scenarios differ in:
   - wind direction (±25° around the measurement, 10 % anywhere) and speed;
   - a fuel multiplier;
   - the ignition point (upwind of the first sensor, usually within ~400 m);
   - the detection lag.
4. **Particle filter (resample-move).**
   - Every detection or lost sensor multiplies each scenario's weight by its likelihood. The
     timing error grows with time (6 min + 20 %).
   - Calm sensors are weighed afresh at each forecast (never counted twice).
   - When the weights collapse, the ensemble is resampled, then moved by Metropolis–Hastings
     steps on prior × likelihood (Gilks & Berzuini 2001).
5. **Forecast.**
   - Probability contours (20 / 50 / 80 %) per horizon, in WGS84.
   - The estimated ignition and its uncertainty.
   - Heading and speed of the head.
   - The wind the alerts point to.
   - The sensors expected next.
   - Confidence: the share of plausible scenarios.

## Measured

- **Speed.** One arrival map on the real 120 × 120 window takes a few ms. A new fire (200
  scenarios) starts in about 1 s; a detection with resample-move takes about 1–2 s.
- **Synthetic recovery** (`tests/test_filter.py` and a 6-seed tuning run). A hidden fire with
  its ignition 160 m from a sensor, and a measured wind 50° off. After three detections:
  - heading error 0°;
  - wind error at most 6°;
  - ignition within 30–160 m.
- **Live, closed loop** (`python -m wamidh_sim.scenario`, real Kroumirie terrain). The
  hidden wind was 192° at 11.8 m/s; the measurement said 210° at 8 m/s. After sensors
  13 → 56 → 199 detected, the model estimated a wind of 190° and a head heading of 15° (true
  ≈ 12°), with the ignition located ± 205 m.

## Known limits

- **Uncalibrated rates.** Fuel rates and the wind and slope factors come from the literature,
  not from Tunisian fires. The Melloula 2023 backtest is still to do.
- **Ambiguous starts.** When a fire starts midway between sensors (about 1 km from each), the
  first detections can fit more than one fire. The ensemble then spreads its probability; later
  detections and calm sensors separate the cases.
- **Wind.** It is uniform over the window and constant in time. There is no spotting and no
  night-time slowdown.
- **Speed is underestimated.** With few detections, a fast fire can be explained by "strong
  wind" or by "very flammable fuel"; the model tends to underestimate wind speed and compensate
  with fuel.

## Tests

```bash
python -m pytest spread/tests      # synthetic grids with known answers + the real rasters if present
```
