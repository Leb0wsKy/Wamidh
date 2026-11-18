import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { fire, sensor, T0 } from '../test/fixtures'
import { SituationCard } from './SituationCard'

const props = {
  incidents: [],
  nodes: [1, 2, 3, 4, 5].map((i) => sensor(i)),
  soundLocked: false,
  spread: null,
  now: T0 + 42_000,
}

describe('SituationCard', () => {
  it('calm: a clear headline and the overview figures', () => {
    render(<SituationCard {...props} />)

    expect(screen.getByRole('heading', { name: 'All clear' })).toBeInTheDocument()
    expect(screen.getByTestId('fig-sensors')).toHaveTextContent('5/5')
    expect(screen.getByTestId('fig-fires')).toHaveTextContent('0')
    expect(screen.getByText('5 gateways')).toBeInTheDocument()
    expect(screen.getByText(/1\.0 % lost/)).toBeInTheDocument()
    expect(screen.getByText('Last report 3 s ago')).toBeInTheDocument()
    expect(screen.getByText('Siren armed')).toBeInTheDocument()
  })

  it('an alert turns the headline amber; a silent sensor shows in the count', () => {
    render(
      <SituationCard
        {...props}
        nodes={[sensor(1, { state: 'ALERT' }), sensor(2, { state: 'OFFLINE' }), sensor(3)]}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Alert in progress' })).toBeInTheDocument()
    expect(screen.getByTestId('fig-sensors')).toHaveTextContent('2/3')
  })

  it('a fire already acknowledged is named under the headline', () => {
    render(<SituationCard {...props} incidents={[fire(9, 4, 'EN_ROUTE')]} />)

    expect(screen.getByRole('heading', { name: 'Fire in progress' })).toBeInTheDocument()
    expect(screen.getByText(/Fire · sensor 4/)).toBeInTheDocument()
  })

  it('asks for one click when the browser blocks the siren', () => {
    render(<SituationCard {...props} soundLocked />)

    expect(screen.getByRole('button', { name: 'Arm the siren' })).toBeInTheDocument()
  })
})
