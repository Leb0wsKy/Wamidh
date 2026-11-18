// Sparkline path for the sensor ledger's temperature trend (drawn as plain SVG).

/** SVG path of a sparkline filling a w x h box (y grows downwards, so high values go up). */
export function sparkPath(values: number[], w: number, h: number): string {
  if (values.length === 0) return ''
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const x = (i: number) => (values.length === 1 ? 0 : (i / (values.length - 1)) * w)
  const y = (v: number) => (hi === lo ? h / 2 : h - ((v - lo) / (hi - lo)) * h)
  const r = (n: number) => Math.round(n * 10) / 10
  return values.map((v, i) => `${i ? 'L' : 'M'}${r(x(i))},${r(y(v))}`).join('')
}
