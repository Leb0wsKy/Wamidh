import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SensorNode } from '../api/types'
import { SensorLedger } from './SensorLedger'

const NOW = Date.parse('2026-10-01T12:00:08Z')
const node = (id: number, extra: Partial<SensorNode> = {}): SensorNode => ({
  id,
  state: 'NORMAL',
  lon: 8.6,
  lat: 36.77,
  last_seen: '2026-10-01T12:00:00Z',
  battery_v: 4.02,
  risk_percentile: 99.3,
  gateway_id: 31,
  readings: { temp_c: 28.04, rh_pct: 41.3, gas_ratio: 0.974, flame: false, fire_prob: 0.036 },
  link: { received: 940, lost: 0, rejected: 0 },
  ...extra,
})
const props = {
  now: NOW,
  trends: { 2: [27.5, 27.9, 28.0] },
  trendMinutes: 60,
  highlightId: null,
  onHover: () => {},
  onSelect: () => {},
  query: '',
  onQuery: () => {},
  total: 200,
}

describe('SensorLedger', () => {
  it('one row per sensor, in the order given, with readings, AI estimate, battery and contact', () => {
    render(
      <SensorLedger
        {...props}
        nodes={[
          node(4, {
            state: 'FIRE',
            readings: { temp_c: 58.2, rh_pct: 9, gas_ratio: 0.29, flame: true, fire_prob: 1 },
          }),
          node(2),
        ]}
      />,
    )

    const rows = screen.getAllByRole('button')
    expect(rows[0]).toHaveTextContent('Fire')
    expect(rows[0]).toHaveTextContent('58.2 °C')
    expect(rows[0]).toHaveTextContent('100 %')
    const calm = within(rows[1]!)
    expect(calm.getByText('28.0 °C')).toBeInTheDocument()
    expect(calm.getByText('41 % · gas 0.97')).toBeInTheDocument()
    expect(calm.getByText('4 %')).toBeInTheDocument()
    expect(calm.getByText('4.02 V')).toBeInTheDocument()
    expect(calm.getByText('8 s ago')).toBeInTheDocument()
    expect(rows[1]!.querySelector('svg path')).not.toBeNull() // the trend line
  })

  it('says how long a silent sensor has been quiet, and when it has no radio link', () => {
    render(
      <SensorLedger
        {...props}
        nodes={[node(3, { state: 'OFFLINE', gateway_id: null })]}
        now={NOW + 12 * 60_000}
      />,
    )

    expect(screen.getByText('Silent for 12:08')).toBeInTheDocument()
    expect(screen.getByText('Out of radio range')).toBeInTheDocument()
  })

  it('centres the map on a sensor when its row is clicked', async () => {
    const onSelect = vi.fn()
    render(<SensorLedger {...props} nodes={[node(2)]} onSelect={onSelect} />)

    await userEvent.click(screen.getByRole('button', { name: /Sensor 2/ }))

    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('has no camera column: the camera result stays on the node (ADR 0001)', () => {
    render(<SensorLedger {...props} nodes={[node(1)]} />)

    expect(screen.queryByText('Camera')).not.toBeInTheDocument()
    expect(screen.queryByTestId('camera')).not.toBeInTheDocument()
  })

  it('searches sensors by number', async () => {
    const onQuery = vi.fn()
    render(<SensorLedger {...props} nodes={[node(2)]} onQuery={onQuery} />)

    await userEvent.type(screen.getByRole('searchbox', { name: 'Find a sensor by number' }), '7')

    expect(onQuery).toHaveBeenCalledWith('7')
  })

  it('says what the list shows: the top-risk sensors, or the search results', () => {
    const { rerender } = render(<SensorLedger {...props} nodes={[node(2)]} />)
    expect(
      screen.getByText('Highest-risk sensors · 1 of 200 · sensors in alarm stay on top'),
    ).toBeInTheDocument()

    rerender(<SensorLedger {...props} nodes={[]} query="999" total={0} />)
    expect(screen.getByText('No sensor numbered 999.')).toBeInTheDocument()

    rerender(<SensorLedger {...props} nodes={[node(2)]} query="2" total={11} />)
    expect(screen.getByText('1 of 11 sensors whose number starts with 2')).toBeInTheDocument()
  })
})
