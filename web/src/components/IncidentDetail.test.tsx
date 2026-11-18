import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { Incident } from '../api/types'
import { IncidentDetail } from './IncidentDetail'

const incident: Incident = {
  id: 7,
  status: 'STATION_NOTIFIED',
  first_node_id: 42,
  estimated_origin: { lon: 8.7, lat: 36.8 },
  created_at: '2026-10-01T12:00:00Z',
  acknowledged_at: null,
  access_point: { lon: 8.71, lat: 36.79, road_type: 'track' },
  node_ids: [42, 43],
  assigned_crew: null,
  events: [
    { ts: '2026-10-01T12:00:00Z', type: 'node_fire', payload: { node_id: 42 } },
    { ts: '2026-10-01T12:00:05Z', type: 'station_notified', payload: {} },
  ],
}
const now = Date.parse('2026-10-01T12:03:20Z')

describe('IncidentDetail', () => {
  it('shows the status, the sensors, the duration and the whole timeline', () => {
    render(<IncidentDetail incident={incident} now={now} onAcknowledge={() => {}} />)

    expect(screen.getByRole('heading', { name: /Sensor 42/ })).toBeInTheDocument()
    expect(screen.getByText('Station notified')).toBeInTheDocument()
    expect(screen.getByText('42, 43')).toBeInTheDocument()
    expect(screen.getByText('3:20')).toBeInTheDocument()
    expect(screen.getByText('forest track')).toBeInTheDocument()
    expect(screen.getByText('Sensor 42 detected a fire')).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('acknowledges with one click, and hides the button once acknowledged', async () => {
    const onAck = vi.fn()
    const { rerender } = render(
      <IncidentDetail incident={incident} now={now} onAcknowledge={onAck} />,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
    expect(onAck).toHaveBeenCalledWith(7)

    rerender(
      <IncidentDetail
        incident={{ ...incident, status: 'ACKNOWLEDGED' }}
        now={now}
        onAcknowledge={onAck}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Acknowledge' })).not.toBeInTheDocument()
  })
})
