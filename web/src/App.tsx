import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { BrowserRouter, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useApi } from './api/context'
import { useOpenIncidents } from './api/queries'
import { Icon } from './components/Icon'
import { LANGUAGES } from './i18n'
import { incidentBadge } from './domain/incident'
import { CrewPage } from './pages/CrewPage'
import { DispatchLayout } from './pages/DispatchLayout'
import { IncidentsPage } from './pages/IncidentsPage'
import { ResidentsPage } from './pages/ResidentsPage'
import { SpreadPage } from './pages/SpreadPage'
import { StationPage } from './pages/StationPage'

// The navigation screen carries the MapLibre GL engine; load it only when a crew presses Go.
const NavigationPage = lazy(() =>
  import('./pages/NavigationPage').then((m) => ({ default: m.NavigationPage })),
)

const LANGUAGE_NAMES: Record<(typeof LANGUAGES)[number], string> = {
  ar: 'العربية',
  fr: 'Français',
  en: 'English',
}

function Header() {
  const { t, i18n } = useTranslation()
  const { connected } = useApi()
  const badge = incidentBadge(useOpenIncidents().data ?? [])
  const tab = ({ isActive }: { isActive: boolean }) =>
    `relative flex h-full items-center px-3 text-[15px] font-medium whitespace-nowrap transition-colors max-sm:px-2 max-sm:text-sm ${
      isActive
        ? 'text-ink after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:bg-ember'
        : 'text-ink-2 hover:text-ink'
    }`

  return (
    <header className="flex h-14 shrink-0 items-stretch gap-2 border-b border-line bg-surface px-4">
      <span className="flex items-center gap-2 text-ink sm:me-4">
        <Icon name="flame" size={22} filled className="text-ember" />
        <span className="hidden text-[17px] font-semibold tracking-tight sm:inline">
          {t('app.title')}
        </span>
      </span>
      <nav className="flex items-stretch overflow-x-auto">
        <NavLink to="/station" className={tab}>
          {t('nav.station')}
        </NavLink>
        {/* Dispatch desk work, like Admin: hidden on phones, where crews have their own list. */}
        <NavLink to="/incidents" className={(p) => `${tab(p)} gap-2 max-sm:hidden`}>
          {t('nav.incidents')}
          {badge.count > 0 && (
            <span
              className={`rounded-full px-1.5 text-xs leading-5 font-semibold tabular-nums ${
                badge.urgent ? 'eg-pulse bg-ember text-white' : 'bg-ink/[0.08] text-ink'
              }`}
            >
              {badge.count}
            </span>
          )}
        </NavLink>
        <NavLink to="/crew" className={tab}>
          {t('nav.crew')}
        </NavLink>
        {/* Desk work, like Incidents: hidden on phones. */}
        <NavLink to="/spread" className={(p) => `${tab(p)} max-sm:hidden`}>
          {t('nav.spread')}
        </NavLink>
        <NavLink to="/residents" className={tab}>
          {t('nav.residents')}
        </NavLink>
      </nav>
      <div className="ms-auto flex items-center gap-3">
        <span
          role="status"
          aria-label={connected ? t('app.live') : t('app.offline')}
          className={`flex items-center gap-2 text-sm font-medium ${connected ? 'text-ink-2' : 'text-ember'}`}
        >
          <span
            aria-hidden
            className={`inline-block size-2 rounded-full ${connected ? 'bg-ok' : 'eg-pulse bg-ember'}`}
          />
          <span className="hidden sm:inline">{connected ? t('app.live') : t('app.offline')}</span>
        </span>
        <label className="flex items-center">
          <span className="sr-only">{t('app.language')}</span>
          <select
            value={i18n.language}
            onChange={(e) => void i18n.changeLanguage(e.target.value)}
            className="h-9 rounded-md border border-line-strong bg-surface px-1.5 text-sm text-ink sm:px-2"
          >
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {LANGUAGE_NAMES[l]}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-full flex-col">
        <Header />
        <main className="min-h-0 flex-1">
          <Routes>
            <Route path="/" element={<Navigate to="/station" replace />} />
            <Route element={<DispatchLayout />}>
              <Route path="/station" element={<StationPage />} />
              <Route path="/incidents" element={<IncidentsPage />} />
            </Route>
            <Route path="/crew" element={<CrewPage />} />
            <Route
              path="/crew/navigate/:id"
              element={
                <Suspense fallback={null}>
                  <NavigationPage />
                </Suspense>
              }
            />
            <Route path="/spread" element={<SpreadPage />} />
            <Route path="/residents" element={<ResidentsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
