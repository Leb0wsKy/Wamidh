import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AlertProposal, Incident } from '../api/types'
import { fire } from '../test/fixtures'
import { PopulationAlert } from './PopulationAlert'

const proposal: AlertProposal = {
  incident_id: 7,
  radius_km: 3,
  zones: [
    {
      id: 2,
      label: 'عين دراهم',
      population: 900,
      risk_level: 'high',
      distance_km: 1.2,
      tower_ids: ['605-2-1-1'],
    },
    {
      id: 5,
      label: 'دوار قرب بلطة',
      population: 120,
      risk_level: 'medium',
      distance_km: 2.5,
      tower_ids: ['605-2-1-1', '605-3-1-9'],
    },
  ],
  people: 1020,
  tower_ids: ['605-2-1-1', '605-3-1-9'],
  headline: 'تحذير: حريق غابة قرب عين دراهم',
  description: 'رُصد حريق غابة',
  instruction: 'اتصلوا بالرقم 198',
}

const acked = fire(7, 1, 'ACKNOWLEDGED')
const broadcastButton = () => screen.getByRole('button', { name: 'Broadcast the alert' })

describe('PopulationAlert', () => {
  it('lists the concerned zones and previews the Arabic message', () => {
    render(<PopulationAlert incident={acked} proposal={proposal} onSend={() => {}} />)

    expect(screen.getByText('عين دراهم')).toBeInTheDocument()
    expect(screen.getByText('1.2 km')).toBeInTheDocument()
    const stat = (name: string) => screen.getByText(name).parentElement as HTMLElement
    expect(within(stat('Residents')).getByText('1,020')).toBeInTheDocument()
    expect(within(stat('Zones')).getByText('2')).toBeInTheDocument()
    expect(within(stat('Cell towers')).getByText('2')).toBeInTheDocument()
    expect(screen.getByText('900 residents')).toBeInTheDocument()
    const preview = screen.getByText('تحذير: حريق غابة قرب عين دراهم')
    expect(preview.closest('[lang="ar"]')).toHaveAttribute('dir', 'rtl')
  })

  it('without known towers, says the alert is targeted by the zone outlines', () => {
    const noTowers = {
      ...proposal,
      tower_ids: [],
      zones: proposal.zones.map((z) => ({ ...z, tower_ids: [] })),
    }
    render(<PopulationAlert incident={acked} proposal={noTowers} onSend={() => {}} />)

    expect(screen.queryByText('Cell towers')).not.toBeInTheDocument()
    expect(screen.getByText(/targeted by the outline of each zone/)).toBeInTheDocument()
    expect(broadcastButton()).toBeEnabled()
  })

  it('stays disabled until the station acknowledges', () => {
    render(
      <PopulationAlert
        incident={fire(7, 1, 'STATION_NOTIFIED')}
        proposal={proposal}
        onSend={() => {}}
      />,
    )

    expect(broadcastButton()).toBeDisabled()
    expect(screen.getByText('Acknowledge the incident first.')).toBeInTheDocument()
  })

  it('asks for confirmation before broadcasting, and can be cancelled', async () => {
    const onSend = vi.fn()
    render(<PopulationAlert incident={acked} proposal={proposal} onSend={onSend} />)

    await userEvent.click(broadcastButton())
    expect(onSend).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await userEvent.click(broadcastButton())
    await userEvent.click(screen.getByRole('button', { name: 'Confirm: alert 1,020 people' }))

    expect(onSend).toHaveBeenCalledTimes(1)
  })

  it('says when the alert went out, and offers an update', () => {
    const sent: Incident = {
      ...acked,
      events: [{ ts: '2026-10-01T12:09:00Z', type: 'public_alert', payload: { people: 1020 } }],
    }
    render(<PopulationAlert incident={sent} proposal={proposal} onSend={() => {}} />)

    expect(screen.getByText(/^Alert broadcast at \d\d:09$/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Broadcast an update' })).toBeEnabled()
  })

  it('says when nobody lives near the fire', () => {
    render(
      <PopulationAlert
        incident={acked}
        proposal={{ ...proposal, zones: [], people: 0, tower_ids: [] }}
        onSend={() => {}}
      />,
    )

    expect(screen.getByText('No inhabited zone within 3 km.')).toBeInTheDocument()
    expect(broadcastButton()).toBeDisabled()
  })
})
