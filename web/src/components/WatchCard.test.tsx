import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { fire, sensor, T0 } from '../test/fixtures'
import { WatchCard } from './WatchCard'

describe('WatchCard', () => {
  it('says all is well when nothing needs attention', () => {
    render(<WatchCard nodes={[sensor(1)]} incidents={[]} now={T0} />)

    expect(screen.getByText('Nothing to report')).toBeInTheDocument()
    expect(screen.getByText('No fire in the last 24 h')).toBeInTheDocument()
  })

  it('names each sensor that needs maintenance, and the last 24 h of activity', () => {
    render(
      <WatchCard
        nodes={[
          sensor(1, { battery_v: 3.42 }),
          sensor(2, { state: 'OFFLINE', last_seen: '2026-10-01T11:00:00Z' }),
          sensor(3, { last_alert_at: '2026-10-01T10:00:00Z' }),
        ]}
        incidents={[fire(9, 3, 'CLOSED'), fire(8, 1, 'FALSE_ALARM')]}
        now={T0}
      />,
    )

    const items = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual([
      expect.stringMatching(/Sensor 2.*Silent for 1:00:00/),
      expect.stringMatching(/Sensor 1.*Low battery.*3\.42 V/),
    ])
    expect(screen.getByTestId('act-fires')).toHaveTextContent('1')
    expect(screen.getByTestId('act-false')).toHaveTextContent('1')
    expect(screen.getByTestId('act-alerted')).toHaveTextContent('1')
    expect(screen.getByText(/Last fire: sensor 3/)).toBeInTheDocument()
  })
})
