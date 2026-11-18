// Dashboard settings in one place (CLAUDE.md: no thresholds or intervals inside components).

export const DASHBOARD = {
  /** window of the temperature trends in the sensor ledger */
  historyMinutes: 60,
  /** how often the history is reloaded; live values arrive over the WebSocket meanwhile */
  historyRefreshMs: 15_000,
  /** sensors listed under the map (all in alarm are always listed, even beyond this) */
  ledgerRows: 10,
} as const

/**
 * When a reading is shown in amber (alert) or ember (fire) on the dashboard. Display only: the
 * fire decision is the node's own `fire_prob` and state.
 * ASSUMPTION: values chosen for a Kroumirie summer (hot afternoons reach the high 30s °C), to be
 * revisited with field data. Gas ratio = gas resistance / the node's clean-air baseline.
 */
export const READING_TONES = {
  temp: { alert: 40, fire: 55 }, // °C, at or above
  rh: { alert: 20 }, // %, at or below: very dry air
  gas: { alert: 0.85, fire: 0.5 }, // ratio, below: smoke lowers the gas resistance
  ai: { alert: 0.3, fire: 0.6 }, // on-node fire probability, at or above
} as const

/**
 * "À surveiller" on the station page: maintenance worth a look.
 * ASSUMPTION: thresholds chosen for a single Li-ion cell (the gauge treats 3.3 V as empty) and a
 * LoRa link where a few lost packets are normal; to be tuned with field data.
 */
export const WATCH = {
  lowBatteryV: 3.5, // at or below
  packetLossPct: 5, // above
} as const

/** Public alerts (ADR 0003). */
export const ALERTS = {
  // Recorded in the audit log as who confirmed the broadcast. A role, not a person: there is
  // no login yet; with accounts this becomes the signed-in dispatcher.
  confirmedBy: 'dispatcher',
  /** how often the Residents tab reloads the alerts in progress */
  refreshMs: 15_000,
} as const
