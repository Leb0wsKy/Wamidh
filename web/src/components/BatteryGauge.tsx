import { batteryLevel } from '../domain/status'

/** Battery as a small gauge plus the measured voltage (the gauge scale is an assumption). */
export function BatteryGauge({ volts }: { volts: number | null }) {
  const level = batteryLevel(volts)
  if (level === null || volts === null) return <span className="text-ink-3">—</span>
  const colour = level < 0.2 ? 'bg-ember' : level < 0.4 ? 'bg-alert-fill' : 'bg-ink-2'
  return (
    <span className="inline-flex items-center gap-2">
      <span aria-hidden className="relative h-2.5 w-7 rounded-[3px] border border-ink-3 p-px">
        <span
          className={`block h-full rounded-[1px] ${colour}`}
          style={{ width: `${level * 100}%` }}
        />
        <span className="absolute -end-[3px] top-[2px] h-1 w-[2px] rounded-e-sm bg-ink-3" />
      </span>
      <span dir="ltr" className="tabular-nums">
        {volts.toFixed(2)} V
      </span>
    </span>
  )
}
