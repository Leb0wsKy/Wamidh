# Backend HTTP + WebSocket API (v1)

Consumed by the web app (`web/src/api/types.ts` mirrors these shapes; keep them in sync).
All paths under `/api/v1`. Coordinates are WGS84 `[lon, lat]`; timestamps UTC ISO-8601.

## Resources

| Method | Path | Returns |
|---|---|---|
| GET | `/nodes` | `Node[]` |
| GET | `/nodes/{id}/telemetry?since=` | `Telemetry[]` |
| GET | `/gateways` | `Gateway[]` |
| GET | `/stations` | `Station[]` |
| GET | `/crews` | `Crew[]` |
| GET | `/incidents` | `Incident[]`, all incidents including closed ones (the history) |
| GET | `/incidents?near=lat,lon&radius_km=5` | `Incident[]` whose estimated origin is within the radius (0 < r ≤ 100 km), nearest first; 422 on bad input, 501 without PostgreSQL + PostGIS |
| GET | `/incidents/{id}` | `Incident` (with `events`) |
| POST | `/incidents/{id}/ack` | `Incident` |
| POST | `/incidents/{id}/assign` `{crew_id}` | `Incident` (a crew takes it; 409 if already taken or not acknowledged) |
| POST | `/incidents/{id}/status` `{status, crew_id}` | `Incident` (only the assigned crew; 409 otherwise) |
| GET | `/incidents/{id}/route?from=lat,lon&crew_id=` | `Route`: from the live GPS (`from`), else from the crew's station (503 if the road network is not loaded, 404 if no road route) |
| GET | `/history?minutes=60&nodes=1,2,3` | `History`: recent readings of the installed sensors (1–1440 min); `nodes` limits it to those sensors (the dashboard asks only for the ones on screen) |
| GET | `/risk-map` | `RiskOverlay` (image URL + bounds) |
| GET | `/incidents/{id}/forecast` | `Forecast` (ADR 0004): spread probability contours per horizon, ignition, head, wind, threatened zones; advisory. 404 unknown incident, 503 without the spread engine |
| GET | `/weather?lat=&lon=` | `WindReading`: wind now (OpenWeatherMap, else last known, else the configured default; `source` says which) |
| GET | `/zones` | GeoJSON FeatureCollection of `AlertZone` (public; ADR 0003) |
| GET | `/towers` | GeoJSON FeatureCollection of `CellTower` (public; OpenCelliD, approximate) |
| GET | `/incidents/{id}/alert-proposal` | `AlertProposal`: zones within `concern_radius_km` of the origin; never sends (404 unknown incident, 501 without PostGIS) |
| POST | `/incidents/{id}/alert` `{confirmed_by}` | `PublicAlertRecord`: a dispatcher-confirmed Cell Broadcast; 409 before acknowledgement, once closed, or with no zone; audit event `public_alert`. Repeats allowed (updates) |
| GET | `/alerts?active=true` | `PublicAlert[]`, newest first; `active` keeps alerts of open incidents. No sensor data, no dispatcher name |
| WS | `/ws` | stream of `LiveEvent` |

## Types

```ts
type NodeState = "NORMAL" | "ALERT" | "FIRE" | "OFFLINE" | "LOST_PROBABLY_BURNED";

interface Node {
  id: number; lon: number; lat: number; state: NodeState;
  last_seen: string | null; battery_v: number | null;
  risk_percentile: number | null;   // from the placement model
  gateway_id: number | null;        // 0/null = no line of sight
  coverage_radius_m: number;        // zone the node is responsible for (not detection range)
  readings: {                        // last reported values
    gas_ratio: number; temp_c: number; rh_pct: number; flame: boolean;
    fire_prob: number;               // on-node verdict; includes the camera (ADR 0001)
  } | {};                            // {} until the node first reports
  last_alert_at: string | null;      // last report in ALERT (UTC)
  last_fire_at: string | null;       // last report in FIRE (UTC)
  access_point: { lon: number; lat: number; road_type: string } | null;  // from the registry
  link: { received: number; lost: number; rejected: number };  // radio link statistics
}

interface Station { id: number; name: string; lon: number; lat: number; source?: string; }

interface Crew { id: number; name: string; station_id: number; }

interface Gateway { id: number; lon: number; lat: number; elevation_m: number; nodes_assigned: number; }

type IncidentStatus = "NEW" | "STATION_NOTIFIED" | "ACKNOWLEDGED" | "EN_ROUTE" | "ON_SITE"
                    | "UNDER_CONTROL" | "CLOSED" | "FALSE_ALARM";

interface IncidentEvent { ts: string; type: string; payload: Record<string, unknown>; }

interface Incident {
  id: number; status: IncidentStatus; first_node_id: number;
  estimated_origin: { lon: number; lat: number } | null;
  created_at: string; acknowledged_at: string | null;
  access_point: { lon: number; lat: number; road_type: string } | null;
  node_ids: number[];               // sensors that detected this fire
  assigned_crew: number | null;     // crew that took it
  events: IncidentEvent[];          // audit log, oldest first
}

interface RiskOverlay { url: string; bounds: [[number, number], [number, number]]; } // [[south, west], [north, east]]

type LiveEvent =
  | { kind: "node"; node: Node }
  | { kind: "incident"; incident: Incident };

/** Recent sensor history. Points are thinned to backend/config/dev.yaml history.max_points
 *  per sensor (evenly sampled), but every reading where the state changes is kept. A gap
 *  longer than silent_after_s[state] between two points means the sensor was silent. */
interface History {
  since: string;  // ISO, UTC
  now: string;
  silent_after_s: Record<"NORMAL" | "ALERT" | "FIRE", number>;
  nodes: {
    node_id: number;
    points: { ts: string; state: NodeState; temp_c: number; rh_pct: number;
              gas_ratio: number; fire_prob: number; battery_v: number }[];  // ts = server receive time
  }[];
}

/** In-app navigation for crews (Go button): offline fastest route on OSM roads
 *  (backend/src/wamidh_backend/routing.py), then the last metres on foot. */
type StepKind = "depart" | "straight" | "slight_left" | "left" | "slight_right" | "right" | "uturn" | "arrive";

interface RouteStep {
  kind: StepKind;
  road: { ref: string | null; name: string | null; fclass: string };  // OSM road taken
  distance_m: number;          // road driven after this manoeuvre
  location: [number, number];  // [lon, lat], a vertex of drive.geometry
}

interface Route {
  incident_id: number;
  origin: { lon: number; lat: number; source: "gps" | "station" };
  target: { node_id: number; lon: number; lat: number };   // the detecting node
  drive: {
    geometry: [number, number][];  // [lon, lat], from the road nearest the origin to the access point
    distance_m: number;
    duration_s: number;            // speeds per road class are ASSUMPTIONS (backend/config/dev.yaml)
    steps: RouteStep[];
  };
  walk: { geometry: [number, number][]; distance_m: number };  // road end -> node, straight line
}
```

Population alerts (ADR 0003; opt-in SMS `/subscriptions` superseded by Cell Broadcast):

```ts
interface AlertZone {          // feature properties; geometry: MultiPolygon (WGS84)
  id: number;
  name: string | null;         // Arabic OSM place name; null for a douar
  near: string | null;         // nearest named place ("douar near X")
  population: number;          // WorldPop 2020 estimate, rounded to 10
  risk_level: "high" | "medium" | "low";
  risk_percentile: number | null;
  building_count: number;
  tower_ids: string[];
}

interface CellTower {          // feature properties; geometry: Point
  id: string;                  // "mcc-net-area-cell"
  radio: string; net: number; range_m: number; samples: number;
}

interface AlertProposal {
  incident_id: number;
  radius_km: number;
  zones: { id: number; label: string; name: string | null; near: string | null;
           population: number; risk_level: string; distance_km: number; tower_ids: string[] }[];
  people: number;
  tower_ids: string[];
  headline: string; description: string; instruction: string;   // Arabic
}

interface PublicAlert {
  id: number; incident_id: number; created_at: string;
  zones: { id: number; label: string }[];
  people: number;
  headline: string; message_ar: string;
  status: "Exercise" | "Actual";   // CAP status; "Exercise" = simulated delivery
  delivery: string;                // "simulated" until a real operator provider exists
  active: boolean;
}
```

Fire spread (ADR 0004). The WebSocket also sends `{"kind": "forecast", "incident_id", "computed_at"}`
every few seconds while an incident burns; clients refetch the forecast.

```ts
interface WindReading { from_deg: number; speed_ms: number; source: string; observed_at: string }

interface Forecast {
  incident_id: number;
  computed_at: string;
  fire_minutes: number;            // since the first detection, in fire time
  time_scale: number;              // 60 in the demo: fire minutes per real minute
  advisory: true;
  closed: boolean;                 // frozen at the end of the incident
  ignition: { lon: number; lat: number; uncertainty_m: number; at: string };
  head: { bearing_deg: number | null; speed_m_min: number };   // where the head runs
  wind: { estimated_from_deg: number; estimated_speed_ms: number;
          observed_from_deg: number; observed_speed_ms: number; source: string };
  wind_reading: WindReading;       // the measurement the ensemble started from
  confidence: { members: number; ess_ratio: number };
  area_ha: Record<"0" | "15" | "30" | "60" | "120", number>;   // burned with p >= 0.5
  horizons: Record<"0" | "15" | "30" | "60" | "120",
    GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon, { p: 0.2 | 0.5 | 0.8; horizon_min: number }>>;
  observed: { node_id: number; event: "FIRE" | "LOST"; at: string }[];
  next_nodes: { node_id: number; p_within_60: number; p_within_120: number; eta_min: number | null }[];
  threatened_zones: { id: number; name: string | null; near: string | null; population: number;
                      risk_level: string; horizon_min: number; p: number }[];
}
```
