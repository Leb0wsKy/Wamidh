# SDD ledger — plan: docs/superpowers/plans/2026-10-05-node-camera-and-map-popup.md
Spec: docs/superpowers/specs/2026-10-05-node-camera-and-map-popup-design.md
Setup: Ruling: no git repository (the team runs git init) — no worktree, no commits, no BASE; ledger kept by hand, commit steps skipped — cost if wrong: changes are not split into commits; the team commits them after git init.
Pre-flight: T1→T2 Telemetry.vision_prob/vision_night consumed by simulator payload: consistent.
Pre-flight: T1→T3 Telemetry.vision_prob/vision_night read by core.handle: consistent.
Pre-flight: T3→T4 Node JSON vision{prob,night,at}, last_alert_at, last_fire_at, access_point, readings.vision_*: matches SensorNode fields in T4 Step 1.
Pre-flight: T4→T5 SensorDetails({node, now, onClose}) used by StationMap; popup.night key used by ledger title: consistent.
Task 1: complete (no commits: no git; tests: contracts/python pytest → 14 passed)
Task 2: Ruling: firmware test helper written as a named function instead of lambda+noqa — same assertions, lint-clean — cost if wrong: none.
Task 2: complete (no commits: no git; tests: simulator pytest → 26 passed; ruff clean)
Task 3: Ruling: api.md Node type lacked readings and link entirely — added them with the new fields — cost if wrong: doc only.
Task 3: complete (no commits: no git; tests: backend pytest → 48 passed; ruff + mypy clean)
Task 4: complete (no commits: no git; tests: web vitest → 84 passed; tsc clean)
Task 5: Ruling: popup opener passed to FocusOn as a useCallback instead of an inline arrow — keeps the effect from re-running each render — cost if wrong: none.
Task 5: complete (no commits: no git; tests: web vitest → 85 passed; tsc, oxlint, build clean)
Task 6: Ruling: restart left the old node child processes running (only the launcher was stopped) — stopped every wamidh_sim process and restarted — cost if wrong: none (dev processes).
Task 6: Ruling: live check found marker DOM elements replaced every second (new icon object per render) and on hover, which lost clicks — icons cached per (sensor, state), highlight toggled in place (mapIcons.ts, tests RED→GREEN) — cost if wrong: highlight briefly missing after a state change until the effect reruns.
Task 6: Ruling: popup was 602 px in a 490 px map (Leaflet's default paragraph margins) — removed the margins, two-column readings, merged access/gateway line → 410 px, marker stays visible — cost if wrong: layout only.
Task 6: Ruling: 'Feu visible 2 %' misread as a visible fire; Arabic popup times had Latin units — wording 'Feu vu par la caméra : p %', units from locale key units.* (tests RED→GREEN) — cost if wrong: copy only.
Task 6: Ruling: live-check script waits 400 ms after × (Leaflet fade-out) before counting popups — test timing, not app behaviour — cost if wrong: none.
Task 6: Ruling: web README /station row was outdated (incidents moved to their own tab) — rewrote it and added the /incidents row — cost if wrong: doc only.
Task 6: complete (no commits: no git; live check in Edge: popup open during live updates, closed by × and Escape, marker reopens, no page errors; web vitest → 89 passed)
Final review: fresh reviewer (opus), whole change; no Critical, 2 Important, 7 Minor.
Final: fixed popup called a burned/offline node's camera 'asleep' — test 'does not call the camera of a burned or offline sensor asleep' RED→GREEN, suite 91/91
Final: fixed popup showed an earlier episode's camera result as current right after entering ALERT — test 'in an alert, an older camera result is not shown as the current one' RED→GREEN, suite 91/91
Final: Ruling: spec said Leaflet's own × restyled; plan and code use closeButton=false plus our own 32 px button — testable and same behaviour — cost if wrong: none.
Final: Ruling: workspace kept (not deleted) — no git history exists yet, so this ledger is the only record — cost if wrong: one scratch folder.
Final: minor (deferred): last alert/fire times set from event messages are rebuilt from telemetry only after a restart.
Final: minor (deferred): FocusOn's map.once('moveend') listener is never removed on a new focus or unmount.
Final: minor (deferred): camera placeholder thresholds are in camera.py, not demo.yaml (labelled ASSUMPTION; same pattern as the existing classifier).
Final: minor (deferred): camera and sensor noise use the same seed per node.
Final: minor (deferred): a node without a camera, in NORMAL, reads 'asleep' (no camera-presence field yet).
Final: minor (deferred): packet_format.md should state vision_night = 0 when vision_prob is null, and copy the airtime parameters from the ADR.
