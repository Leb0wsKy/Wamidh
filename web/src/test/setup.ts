import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import i18n from '../i18n'

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(cleanup)

// Tests assert English labels; the app itself defaults to French.
await i18n.changeLanguage('en')
