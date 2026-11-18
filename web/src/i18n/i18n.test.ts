import { describe, expect, it } from 'vitest'
import ar from './locales/ar.json'
import en from './locales/en.json'
import fr from './locales/fr.json'
import i18n, { defaultLanguage, directionOf } from './index'

function keys(obj: object, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'object' && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  )
}

describe('locales', () => {
  it('Arabic and French translate every English key', () => {
    const reference = keys(en).sort()
    expect(keys(ar).sort()).toEqual(reference)
    expect(keys(fr).sort()).toEqual(reference)
  })
})

describe('product name', () => {
  it('is Wamidh, written in Arabic in the Arabic interface', () => {
    expect(en.app.title).toBe('Wamidh')
    expect(fr.app.title).toBe('Wamidh')
    expect(ar.app.title).toBe('وميض')
  })

  it('names the browser tab in the chosen language', async () => {
    await i18n.changeLanguage('ar')
    expect(document.title).toBe('وميض')
    await i18n.changeLanguage('fr')
    expect(document.title).toBe('Wamidh')
  })
})

describe('directionOf', () => {
  it('is right-to-left for Arabic only', () => {
    expect(directionOf('ar')).toBe('rtl')
    expect(directionOf('fr')).toBe('ltr')
    expect(directionOf('en')).toBe('ltr')
  })
})

describe('keys used in the code', () => {
  it('exist in the locales (catches a section overwritten or renamed)', () => {
    const sources = import.meta.glob<string>(['../**/*.{ts,tsx}', '!../**/*.test.*'], {
      query: '?raw',
      import: 'default',
      eager: true,
    })
    const known = new Set(keys(en))
    const used = Object.values(sources).flatMap((code) =>
      [...code.matchAll(/\bt(?:itleKey=|\()\s*['"]([a-zA-Z]+\.[a-zA-Z_.]+)['"]/g)].map(
        (m) => m[1]!,
      ),
    )
    expect(used.length).toBeGreaterThan(20)
    expect(used.filter((k) => !known.has(k))).toEqual([])
  })
})

describe('defaultLanguage', () => {
  it('is Arabic on the public residents page, French at the station', () => {
    expect(defaultLanguage('/residents')).toBe('ar')
    expect(defaultLanguage('/station')).toBe('fr')
    expect(defaultLanguage('/')).toBe('fr')
  })
})
