import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Incident } from '../api/types'
import { IncidentList } from './IncidentList'

const inc = (id: number, node: number, status: Incident['status']): Incident => ({
  id,
  status,
  first_node_id: node,
  estimated_origin: null,
  created_at: '2026-10-01T12:00:00Z',
  acknowledged_at: null,
  access_point: null,
  node_ids: [node],
  assigned_crew: id === 5 ? 1 : null,
  events: [],
})
// Already in dispatch order: burning first, then under control.
const list = [inc(5, 3, 'EN_ROUTE'), inc(4, 2, 'STATION_NOTIFIED'), inc(2, 1, 'UNDER_CONTROL')]

describe('IncidentList', () => {
  it('groups fires in progress and fires under control, and marks the selected one', () => {
    render(
      <IncidentList
        incidents={list}
        selectedId={4}
        onSelect={() => {}}
        crewName={(id) => `Crew ${id}`}
        now={Date.parse('2026-10-01T12:01:00Z')}
      />,
    )

    const live = screen.getByRole('region', { name: 'In progress' })
    expect(
      within(live)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([expect.stringContaining('Sensor 3'), expect.stringContaining('Sensor 2')])
    expect(within(live).getAllByRole('button')[0]).toHaveTextContent('Crew 1')
    const settled = screen.getByRole('region', { name: 'Under control' })
    expect(within(settled).getByRole('button')).toHaveTextContent('Sensor 1')
    expect(screen.getByRole('button', { current: true })).toHaveTextContent('Sensor 2')
  })

  it('opens an incident when clicked', async () => {
    const onSelect = vi.fn()
    render(
      <IncidentList
        incidents={list}
        selectedId={4}
        onSelect={onSelect}
        crewName={(id) => `Crew ${id}`}
        now={0}
      />,
    )

    await userEvent.click(screen.getByRole('button', { name: /Sensor 1/ }))

    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('shows past incidents in their own group, after the live ones', () => {
    render(
      <IncidentList
        incidents={[...list, inc(1, 5, 'CLOSED'), inc(0, 6, 'FALSE_ALARM')]}
        selectedId={4}
        onSelect={() => {}}
        crewName={(id) => `Crew ${id}`}
        now={0}
      />,
    )

    const closed = screen.getByRole('region', { name: 'Closed' })
    expect(
      within(closed)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual([expect.stringContaining('Sensor 5'), expect.stringContaining('Sensor 6')])
    expect(within(closed).getByText('False alarm')).toBeInTheDocument()
  })
})
