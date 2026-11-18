import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import ar from './locales/ar.json'
import en from './locales/en.json'
import fr from './locales/fr.json'

export const LANGUAGES = ['ar', 'fr', 'en'] as const
export type Language = (typeof LANGUAGES)[number]

const STORAGE_KEY = 'wamidh.lang'

export function directionOf(lng: string): 'rtl' | 'ltr' {
  return lng === 'ar' ? 'rtl' : 'ltr'
}

function storedLanguage(): Language | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return LANGUAGES.includes(v as Language) ? (v as Language) : null
  } catch {
    return null
  }
}

/** First visit: residents read Arabic (the public page), the station works in French. */
export function defaultLanguage(path: string): Language {
  return path.startsWith('/residents') ? 'ar' : 'fr'
}

/** Keep <html lang dir> and the tab title in sync so Arabic lays out right-to-left. */
function applyToDocument(lng: string): void {
  document.documentElement.lang = lng
  document.documentElement.dir = directionOf(lng)
  document.title = i18n.t('app.title', { lng })
  try {
    localStorage.setItem(STORAGE_KEY, lng)
  } catch {
    // private mode: language simply is not remembered
  }
}

void i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, fr: { translation: fr }, en: { translation: en } },
  lng: storedLanguage() ?? defaultLanguage(location.pathname),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})
i18n.on('languageChanged', applyToDocument)
applyToDocument(i18n.language)

export default i18n
