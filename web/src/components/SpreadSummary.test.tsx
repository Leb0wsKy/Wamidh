import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { Forecast } from '../api/types'
import { SensorsOutlook, SpreadSummary, ThreatenedZones } from './SpreadSummary'

const forecast: Forecast = {
  incident_id: 7,
  computed_at: '2026-10-01T12:10:00Z',
  fire_minutes: 34,
  time_scale: 60,
  advisory: true,
  closed: false,
  ignition: { lon: 8.66, lat: 36.82, uncertainty_m: 180, at: '2026-10-01T11:58:00Z' },
  head: { bearing_deg: 92, speed_m_min: 7.1 },
  wind: {
    estimated_from_deg: 268,
    estimated_speed_ms: 6.4,
    observed_from_deg: 310,
    observed_speed_ms: 2.7,
    source: 'openweathermap',
  },
  wind_reading: {
    from_deg: 310,
    speed_ms: 2.7,
    source: 'openweathermap',
    observed_at: '2026-10-01T12:00:00Z',
  },
  confidence: { members: 200, ess_ratio: 0.82 },
  area_ha: { '0': 2, '15': 4, '30': 7, '60': 15, '120': 40 },
  horizons: {},
  observed: [
    { node_id: 12, event: 'FIRE', at: '2026-10-01T12:00:00Z' },
    { node_id: 14, event: 'FIRE', at: '2026-10-01T12:05:00Z' },
    { node_id: 12, event: 'LOST', at: '2026-10-01T12:08:00Z' },
  ],
  next_nodes: [{ node_id: 15, p_within_60: 0.7, p_within_120: 0.9, eta_min: 25.2 }],
  threatened_zones: [
    {
      id: 3,
      name: null,
      near: 'بلطة',
      population: 450,
      risk_level: 'high',
      horizon_min: 60,
      p: 0.5,
    },
  ],
}

describe('SpreadSummary', () => {
  it('says where the head runs, how fast, and from which wind', () => {
    render(<SpreadSummary forecast={forecast} />)

    expect(screen.getByRole('heading', { name: 'Heading east' })).toBeInTheDocument()
    expect(screen.getByText('~7 m/min')).toBeInTheDocument()
    expect(screen.getByText(/from the west · 23 km\/h/)).toBeInTheDocument() // estimated
    expect(
      screen.getByText(/Measured: from the north-west · 10 km\/h \(OpenWeatherMap\)/),
    ).toBeInTheDocument()
    expect(screen.getByText(/High · 82 % of 200 scenarios/)).toBeInTheDocument()
    expect(screen.queryByText(/time accelerated/i)).not.toBeInTheDocument()
    expect(screen.getByText(/Advisory: decisions stay with the crews/)).toBeInTheDocument()
  })

  it('says when the forecast is frozen at the end of the incident', () => {
    render(<SpreadSummary forecast={{ ...forecast, closed: true, time_scale: 1 }} />)

    expect(screen.getByText(/Incident closed: forecast at its last moment/)).toBeInTheDocument()
    expect(screen.queryByText(/time accelerated/i)).not.toBeInTheDocument()
  })
})

describe('SensorsOutlook', () => {
  it('lists what the sensors saw and which one should detect next', () => {
    render(<SensorsOutlook forecast={forecast} />)

    const seen = screen.getAllByRole('listitem').map((li) => li.textContent)
    expect(seen[0]).toMatch(/Sensor 12.*fire detected/)
    expect(seen[2]).toMatch(/Sensor 12.*lost in the fire/)
    expect(seen[3]).toMatch(/Sensor 15.*~25 min.*70 % within 1 h/)
  })
})

describe('ThreatenedZones', () => {
  it('names the inhabited zones in the fire path, with when and how likely', () => {
    render(
      <MemoryRouter>
        <ThreatenedZones forecast={forecast} />
      </MemoryRouter>,
    )

    const item = screen.getByRole('listitem')
    expect(within(item).getByText('Douar near بلطة')).toBeInTheDocument()
    expect(item).toHaveTextContent(/450.*within 60 min.*≥ 50 %/)
    expect(screen.getByRole('link', { name: /Residents tab/ })).toHaveAttribute(
      'href',
      '/residents',
    )
  })

  it('says when no inhabited zone is in the path', () => {
    render(
      <MemoryRouter>
        <ThreatenedZones forecast={{ ...forecast, threatened_zones: [] }} />
      </MemoryRouter>,
    )

    expect(screen.getByText('No inhabited zone in the fire path within 2 h.')).toBeInTheDocument()
  })
})
