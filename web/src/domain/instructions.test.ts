import { describe, expect, it } from 'vitest'
import i18n from '../i18n'
import { formatDistance, instruction, roadLabel } from './instructions'

const t = i18n.t.bind(i18n)

describe('roadLabel', () => {
  it('prefers the road number, then its name, then the kind of road', () => {
    expect(roadLabel({ ref: 'RN17', name: 'Route de Tabarka', fclass: 'primary' }, t)).toBe('RN17')
    expect(roadLabel({ ref: null, name: 'Route de Tabarka', fclass: 'primary' }, t)).toBe(
      'Route de Tabarka',
    )
    expect(roadLabel({ fclass: 'track_grade3' }, t)).toBe('forest track')
    expect(roadLabel({}, t)).toBe('the road')
  })
})

describe('instruction', () => {
  it('turns a step into a sentence', () => {
    expect(instruction({ kind: 'left', road: { ref: 'RN17' } }, t)).toBe('Turn left onto RN17')
    expect(instruction({ kind: 'uturn', road: {} }, t)).toBe('Make a U-turn')
  })
})

describe('formatDistance', () => {
  it('rounds to what a driver can use', () => {
    expect(formatDistance(47, 'en')).toBe('50 m')
    expect(formatDistance(349, 'en')).toBe('350 m')
    expect(formatDistance(1234, 'en')).toBe('1.2 km')
    expect(formatDistance(1234, 'fr')).toBe('1,2 km')
    expect(formatDistance(15_480, 'en')).toBe('15 km')
  })
})
