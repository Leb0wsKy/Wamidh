import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Incident } from '../api/types'
import { CrewIncidentCard } from './CrewIncidentCard'

const incident: Incident = {
  id: 3,
  status: 'ACKNOWLEDGED',
  first_node_id: 12,
  estimated_origin: { lon: 8.7, lat: 36.8 },
  created_at: '2026-10-01T12:00:00Z',
  acknowledged_at: '2026-10-01T12:01:00Z',
  access_point: { lon: 8.71, lat: 36.79, road_type: 'track' },
  node_ids: [12],
  assigned_crew: 1,
  events: [],
}

describe('CrewIncidentCard', () => {
  it('Go starts in-app navigation instead of opening another app', async () => {
    const onGo = vi.fn()
    render(<CrewIncidentCard incident={incident} position={null} onStatus={() => {}} onGo={onGo} />)

    await userEvent.click(screen.getByRole('button', { name: 'Go' }))

    expect(onGo).toHaveBeenCalledWith(3)
    expect(screen.queryByRole('link')).toBeNull()
  })

  it('names the road type in words, not as an OSM code', () => {
    render(
      <CrewIncidentCard incident={incident} position={null} onStatus={() => {}} onGo={() => {}} />,
    )

    expect(screen.getByText('Leave the vehicle at the forest track')).toBeInTheDocument()
  })

  it('shows the distance when the phone position is known', () => {
    render(
      <CrewIncidentCard
        incident={incident}
        position={{ lon: 8.71, lat: 36.7 }}
        onStatus={() => {}}
        onGo={() => {}}
      />,
    )

    expect(screen.getByText(/10\.0 km/)).toBeInTheDocument()
  })

  it('before arrival offers Go and false alarm only', async () => {
    const onStatus = vi.fn()
    render(
      <CrewIncidentCard incident={incident} position={null} onStatus={onStatus} onGo={() => {}} />,
    )

    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Go', 'False alarm'])
    await userEvent.click(screen.getByRole('button', { name: 'False alarm' }))
    expect(onStatus).toHaveBeenCalledWith(3, 'FALSE_ALARM')
  })

  it('once on site, only under control remains', async () => {
    const onStatus = vi.fn()
    render(
      <CrewIncidentCard
        incident={{ ...incident, status: 'ON_SITE' }}
        position={null}
        onStatus={onStatus}
        onGo={() => {}}
      />,
    )

    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['Under control'])
    await userEvent.click(screen.getByRole('button', { name: 'Under control' }))
    expect(onStatus).toHaveBeenCalledWith(3, 'UNDER_CONTROL')
  })
})
