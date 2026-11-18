import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { AlertProposal, Incident } from '../api/types'
import { fire } from '../test/fixtures'
import { JournalCard } from './JournalCard'
import { PopulationCard } from './PopulationCard'

const proposal: AlertProposal = {
  incident_id: 8,
  radius_km: 3,
  zones: [
    {
      id: 2,
      label: 'عين دراهم',
      population: 4520,
      risk_level: 'high',
      distance_km: 1.3,
      tower_ids: [],
    },
  ],
  people: 4520,
  tower_ids: [],
  headline: '',
  description: '',
  instruction: '',
}
const summary = { zones: 143, people: 131110, high: 103 }
const inRouter = (ui: React.ReactNode) => render(<MemoryRouter>{ui}</MemoryRouter>)

describe('PopulationCard', () => {
  it('during a fire: the residents concerned, and that no alert went out yet', () => {
    inRouter(
      <PopulationCard fire={fire(8, 1, 'ACKNOWLEDGED')} proposal={proposal} summary={summary} />,
    )

    expect(screen.getAllByText('4,520')).toHaveLength(2) // the total, and its only zone
    expect(screen.getByText('عين دراهم')).toBeInTheDocument()
    expect(screen.getByText('Public alert not sent')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Prepare the alert/ })).toHaveAttribute(
      'href',
      '/residents',
    )
  })

  it('says when the alert went out', () => {
    const sent: Incident = {
      ...fire(8, 1, 'ACKNOWLEDGED'),
      events: [{ ts: '2026-10-01T12:09:00Z', type: 'public_alert', payload: { people: 4520 } }],
    }
    inRouter(<PopulationCard fire={sent} proposal={proposal} summary={summary} />)

    expect(screen.getByText(/Alert broadcast at \d\d:09/)).toBeInTheDocument()
  })

  it('with no fire: the zones being watched', () => {
    inRouter(<PopulationCard fire={null} proposal={undefined} summary={summary} />)

    expect(screen.getByText('143')).toBeInTheDocument()
    expect(screen.getByText('131,110')).toBeInTheDocument()
    expect(screen.getByText('103')).toBeInTheDocument()
  })
})

describe('JournalCard', () => {
  it('lists the latest events with their incident', () => {
    const inc: Incident = {
      ...fire(8, 1, 'ACKNOWLEDGED'),
      events: [
        { ts: '2026-10-01T12:00:00Z', type: 'node_fire', payload: { node_id: 1 } },
        { ts: '2026-10-01T12:02:00Z', type: 'acknowledged', payload: {} },
      ],
    }
    render(<JournalCard incidents={[inc]} />)

    const items = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(items[0]).toMatch(/Acknowledged by the station.*#8/)
    expect(items[1]).toMatch(/Sensor 1 detected a fire/)
  })

  it('says when nothing happened yet', () => {
    render(<JournalCard incidents={[]} />)

    expect(screen.getByText('No event yet.')).toBeInTheDocument()
  })
})
