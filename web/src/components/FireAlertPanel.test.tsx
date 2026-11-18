import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AlertProposal } from '../api/types'
import { fire } from '../test/fixtures'
import { FireAlertPanel } from './FireAlertPanel'

const proposal: AlertProposal = {
  incident_id: 8,
  radius_km: 3,
  zones: [
    {
      id: 2,
      label: 'عين دراهم',
      population: 900,
      risk_level: 'high',
      distance_km: 1.2,
      tower_ids: [],
    },
  ],
  people: 900,
  tower_ids: [],
  headline: 'تحذير',
  description: 'رُصد حريق غابة',
  instruction: '198',
}

describe('FireAlertPanel', () => {
  it('offers one tab per open fire and shows the alert of the chosen one', async () => {
    const onSelect = vi.fn()
    render(
      <FireAlertPanel
        incidents={[fire(8, 3, 'ACKNOWLEDGED'), fire(5, 1, 'EN_ROUTE')]}
        selectedId={8}
        onSelect={onSelect}
        proposal={proposal}
        onSend={() => {}}
      />,
    )

    expect(screen.getByRole('tab', { name: /Sensor 3/ })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('button', { name: 'Broadcast the alert' })).toBeEnabled()
    await userEvent.click(screen.getByRole('tab', { name: /Sensor 1/ }))
    expect(onSelect).toHaveBeenCalledWith(5)
  })

  it('needs the station to acknowledge first', () => {
    render(
      <FireAlertPanel
        incidents={[fire(8, 3, 'STATION_NOTIFIED')]}
        selectedId={8}
        onSelect={() => {}}
        proposal={proposal}
        onSend={() => {}}
      />,
    )

    expect(screen.getByRole('button', { name: 'Broadcast the alert' })).toBeDisabled()
  })
})
