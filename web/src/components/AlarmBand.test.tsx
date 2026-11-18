import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { fire, T0 } from '../test/fixtures'
import { AlarmBand } from './AlarmBand'

describe('AlarmBand', () => {
  it('shows nothing while no fire waits for the station', () => {
    const { container } = render(
      <AlarmBand incidents={[fire(3, 2, 'EN_ROUTE')]} now={T0} onAcknowledge={() => {}} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('a fire waiting for the station: the sensor, the time and one action', async () => {
    const onAck = vi.fn()
    render(
      <AlarmBand
        incidents={[fire(21, 3, 'STATION_NOTIFIED'), fire(20, 4, 'NEW')]}
        now={T0 + 42_000}
        onAcknowledge={onAck}
      />,
    )

    const band = screen.getByRole('alert')
    expect(band).toHaveTextContent('Fire · sensor 3')
    expect(band).toHaveTextContent('0:42')
    expect(band).toHaveTextContent('+1 waiting')
    await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    expect(onAck).toHaveBeenCalledWith(21)
  })
})
