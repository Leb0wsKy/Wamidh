import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { SensorNode } from '../api/types'
import i18n from '../i18n'
import { SensorDetails } from './SensorDetails'

const NOW = Date.parse('2026-10-05T12:10:00Z')
const node: SensorNode = {
  id: 4,
  state: 'ALERT',
  lon: 8.601508,
  lat: 36.786972,
  last_seen: '2026-10-05T12:09:52Z',
  battery_v: 4.02,
  risk_percentile: 99.3,
  gateway_id: 33,
  readings: { temp_c: 41.3, rh_pct: 21, gas_ratio: 0.71, flame: false, fire_prob: 0.55 },
  last_alert_at: '2026-10-05T12:09:52Z',
  last_fire_at: null,
  access_point: { lon: 8.6036, lat: 36.7888, road_type: 'track' },
  link: { received: 900, lost: 3, rejected: 0 },
}
const tile = (name: string) => screen.getByTestId(`tile-${name}`)

describe('SensorDetails', () => {
  it('shows each reading as a tile, coloured only when it points to fire', () => {
    render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)

    expect(tile('temp')).toHaveTextContent('41.3 °C')
    expect(tile('temp')).toHaveAttribute('data-tone', 'alert')
    expect(tile('rh')).toHaveTextContent('21 %')
    expect(tile('rh')).toHaveAttribute('data-tone', 'normal')
    expect(tile('gas')).toHaveTextContent('0.71')
    expect(within(tile('gas')).getByText('smoke')).toBeInTheDocument()
    expect(tile('flame')).toHaveTextContent('No')
    expect(tile('flame')).toHaveAttribute('data-tone', 'normal')
    expect(tile('ai')).toHaveTextContent('55 %')
    expect(tile('ai')).toHaveAttribute('data-tone', 'alert')
  })

  it('a flame seen by the IR sensor is shown in ember', () => {
    render(
      <SensorDetails
        node={{ ...node, readings: { ...node.readings, flame: true } }}
        now={NOW}
        onClose={() => {}}
      />,
    )

    expect(tile('flame')).toHaveTextContent('Yes')
    expect(tile('flame')).toHaveAttribute('data-tone', 'fire')
  })

  it('shows no camera information: it stays on the node (ADR 0001)', () => {
    render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)

    expect(screen.queryByText(/camera/i)).not.toBeInTheDocument()
  })

  it('shows state, location, history and health', () => {
    render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: /Sensor 4/ })).toBeInTheDocument()
    expect(screen.getByText('Alert')).toBeInTheDocument()
    expect(screen.getByText('36.78697, 8.60151')).toBeInTheDocument()
    expect(screen.getByText('Access: forest track')).toBeInTheDocument()
    expect(screen.getByText('Gateway 33')).toBeInTheDocument()
    expect(screen.getByText('Last fire').nextSibling).toHaveTextContent('never')
    expect(screen.getByText('Last alert').nextSibling).toHaveTextContent('05/10 13:09 · 8 s ago')
    expect(screen.getByText('4.02 V')).toBeInTheDocument()
    expect(screen.getByText('3 lost')).toBeInTheDocument()
    expect(screen.getByTitle('Contact')).toHaveTextContent('8 s ago')
  })

  it('shows dashes before the sensor first reports', () => {
    render(<SensorDetails node={{ ...node, readings: {} }} now={NOW} onClose={() => {}} />)

    expect(tile('temp')).toHaveTextContent('—')
    expect(tile('ai')).toHaveTextContent('—')
  })

  it('closes with the × button', async () => {
    const onClose = vi.fn()
    render(<SensorDetails node={node} now={NOW} onClose={onClose} />)

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClose).toHaveBeenCalledOnce()
  })

  it('reads right to left in Arabic, with Arabic time units', async () => {
    await i18n.changeLanguage('ar')
    const { container } = render(<SensorDetails node={node} now={NOW} onClose={() => {}} />)
    expect(container.firstElementChild).toHaveAttribute('dir', 'rtl')
    expect(screen.getByTitle('آخر اتصال')).toHaveTextContent('منذ 8 ث')
    await i18n.changeLanguage('en')
  })
})
