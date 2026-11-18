import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AlertZoneProps, CellTower, PublicAlert } from '../api/types'
import { PhoneAlertCard } from './PhoneAlertCard'
import { ZonePanel } from './ZonePanel'

const zone: AlertZoneProps = {
  id: 5,
  name: null,
  near: 'بلطة',
  population: 21620,
  risk_level: 'high',
  risk_percentile: 94.2,
  building_count: 432,
  tower_ids: ['605-2-1-1'],
}
const tower: CellTower = {
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [8.7, 36.8] },
  properties: { id: '605-2-1-1', radio: 'LTE', net: 2, range_m: 1500, samples: 12 },
}
const alert: PublicAlert = {
  id: 3,
  incident_id: 7,
  created_at: '2026-10-01T12:09:00Z',
  zones: [{ id: 5, label: 'دوار قرب بلطة' }],
  people: 21620,
  headline: 'تحذير: حريق غابة قرب دوار قرب بلطة',
  message_ar: 'تحذير: حريق غابة قرب دوار قرب بلطة\nرُصد حريق غابة\nاتصلوا بالرقم 198',
  status: 'Exercise',
  delivery: 'simulated',
  active: true,
}

describe('ZonePanel', () => {
  it('shows the zone, its people, its risk and the towers that serve it', () => {
    render(<ZonePanel zone={zone} towers={[tower]} alert={undefined} onClose={() => {}} />)

    expect(screen.getByRole('heading', { name: 'Douar near بلطة' })).toBeInTheDocument()
    expect(screen.getByText('21,620')).toBeInTheDocument()
    expect(screen.getByText('High')).toBeInTheDocument()
    expect(screen.getByText(/percentile 94/)).toBeInTheDocument()
    expect(screen.getByText(/LTE · 605-2-1-1/)).toBeInTheDocument()
    expect(screen.getByText('No alert for this zone.')).toBeInTheDocument()
  })

  it('shows the alert the zone received, and closes', async () => {
    const onClose = vi.fn()
    render(<ZonePanel zone={zone} towers={[]} alert={alert} onClose={onClose} />)

    expect(
      screen.getByText('None listed by OpenCelliD: targeted by its outline'),
    ).toBeInTheDocument()
    expect(screen.getByText('Alert in progress')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('PhoneAlertCard', () => {
  it('shows the Arabic text as received, as a phone shows it', () => {
    render(<PhoneAlertCard alert={alert} />)

    const text = screen.getByText(/اتصلوا بالرقم 198/)
    expect(text.closest('[lang="ar"]')).toHaveAttribute('dir', 'rtl')
    expect(screen.getByText('Emergency alert')).toBeInTheDocument()
    expect(screen.queryByText(/simulation/i)).not.toBeInTheDocument()
  })
})
