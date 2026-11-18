import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Incident } from '../api/types'
import { CrewFireSummary } from './CrewFireSummary'

const base = {
  id: 5,
  first_node_id: 2,
  estimated_origin: { lon: 8.6, lat: 36.77 },
  created_at: '2026-10-01T12:00:00Z',
  acknowledged_at: '2026-10-01T12:00:30Z',
  access_point: null,
  node_ids: [2],
  events: [],
} satisfies Partial<Incident>

describe('CrewFireSummary', () => {
  it('offers an available fire to take', async () => {
    const onTake = vi.fn()
    render(
      <CrewFireSummary
        incident={{ ...base, status: 'ACKNOWLEDGED', assigned_crew: null }}
        crewName={() => ''}
        onTake={onTake}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Take this mission' }))

    expect(onTake).toHaveBeenCalledWith(5)
  })

  it('shows who took a fire, with nothing to click', () => {
    render(
      <CrewFireSummary
        incident={{ ...base, status: 'EN_ROUTE', assigned_crew: 2 }}
        crewName={(id) => `Crew ${id}`}
        onTake={() => {}}
      />,
    )

    expect(screen.getByText('Taken by Crew 2')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('says when the station has not acknowledged yet', () => {
    render(
      <CrewFireSummary
        incident={{
          ...base,
          status: 'STATION_NOTIFIED',
          assigned_crew: null,
          acknowledged_at: null,
        }}
        crewName={() => ''}
        onTake={() => {}}
      />,
    )

    expect(screen.getByText('Waiting for the station to acknowledge')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
