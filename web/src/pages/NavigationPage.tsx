// In-app turn-by-turn navigation for a crew (the Go button). The route comes from the
// backend's offline road graph, so it works without Google Maps and without leaving the app.

import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { useApi } from '../api/context'
import { DriveMap } from '../components/DriveMap'
import { Icon, type IconName } from '../components/Icon'
import { useOpenIncidents, useSetStatus, useStations } from '../api/queries'
import type { LonLat, StepKind } from '../api/types'
import {
  headingAt,
  headingTo,
  pointAlong,
  prepare,
  progress,
  simulatedPosition,
} from '../domain/guidance'
import type { Progress } from '../domain/guidance'
import { crewActions } from '../domain/incident'
import { formatDistance, instruction } from '../domain/instructions'
import { distanceKm } from '../domain/navigation'
import { useMyCrew, usePosition } from './crewDevice'

/** a GPS fix further than this from the fire is not "in the area" (e.g. a laptop elsewhere) */
const IN_AREA_KM = 60
/** wait this long for a first GPS fix before routing from the station */
const GPS_WAIT_MS = 4000
const OFF_ROUTE_M = 50
const OFF_ROUTE_FIXES = 3
const REROUTE_EVERY_MS = 15_000
/** announce the next manoeuvre again when it gets this close */
const PREPARE_M = 200
const DEMO_SPEEDUP = 10
const DEMO_TICK_MS = 250
/** typical interval between phone GPS fixes */
const GPS_UPDATE_MS = 1000
const VOICE_KEY = 'wamidh.voice'

const ARROW: Record<StepKind | 'walk' | 'arrived', IconName> = {
  depart: 'straight',
  straight: 'straight',
  slight_left: 'slight_left',
  left: 'left',
  slight_right: 'slight_right',
  right: 'right',
  uturn: 'uturn',
  arrive: 'arrive',
  walk: 'walk',
  arrived: 'check',
}
const SPEECH_LANG: Record<string, string> = { ar: 'ar', fr: 'fr-FR', en: 'en-GB' }

function readVoice(): boolean {
  try {
    return localStorage.getItem(VOICE_KEY) !== 'off'
  } catch {
    return true
  }
}

function clock(inSeconds: number, lang: string): string {
  return new Intl.DateTimeFormat(lang === 'ar' ? 'ar-TN' : lang, {
    timeZone: 'Africa/Tunis',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date(Date.now() + inSeconds * 1000))
}

export function NavigationPage() {
  const { t, i18n } = useTranslation()
  const lang = i18n.language
  const navigate = useNavigate()
  const { api } = useApi()
  const incidentId = Number(useParams().id)
  const [myCrew] = useMyCrew()
  const incidents = useOpenIncidents()
  const incident = incidents.data?.find((i) => i.id === incidentId)
  const stations = useStations().data ?? []
  const setStatus = useSetStatus()
  const gps = usePosition(0)

  // Where the route starts: the phone's GPS when it is in the area, else the crew's station.
  const target = incident?.access_point ?? incident?.estimated_origin ?? null
  const gpsInArea = gps !== null && target !== null && distanceKm(gps, target) < IN_AREA_KM
  const [from, setFrom] = useState<LonLat | 'station' | null>(null)
  useEffect(() => {
    if (gpsInArea && (from === null || from === 'station')) setFrom(gps)
  }, [gpsInArea, gps, from])
  useEffect(() => {
    const timer = setTimeout(() => setFrom((f) => f ?? 'station'), GPS_WAIT_MS)
    return () => clearTimeout(timer)
  }, [])

  const routeQuery = useQuery({
    queryKey: [
      'route',
      incidentId,
      from === 'station' ? 'station' : [from?.lat, from?.lon],
      myCrew,
    ],
    queryFn: () =>
      api.route(
        incidentId,
        from && from !== 'station' ? { from } : { crewId: myCrew ?? undefined },
      ),
    enabled: from !== null && incident !== undefined,
    staleTime: Infinity,
    retry: 1,
    placeholderData: keepPreviousData,
  })
  const route = routeQuery.data
  const nav = useMemo(() => (route ? prepare(route) : null), [route])

  // Demo playback, time-accelerated, for rehearsing without a vehicle.
  const [simStart, setSimStart] = useState<number | null>(null)
  const [simPos, setSimPos] = useState<LonLat | null>(null)
  useEffect(() => {
    if (simStart === null || !nav) return
    const timer = setInterval(() => {
      setSimPos(simulatedPosition(nav, ((Date.now() - simStart) / 1000) * DEMO_SPEEDUP))
    }, DEMO_TICK_MS)
    return () => clearInterval(timer)
  }, [simStart, nav])
  const simulating = simStart !== null
  const live = simulating ? simPos : from !== 'station' && gpsInArea ? gps : null

  const lastAlong = useRef<number | undefined>(undefined)
  useEffect(() => {
    lastAlong.current = undefined // a new route starts from zero
  }, [nav])
  const prog: Progress | null = nav
    ? progress(nav, live ?? pointAlong(nav, 0), live ? lastAlong.current : undefined)
    : null
  useEffect(() => {
    if (live && prog) lastAlong.current = prog.alongM
  })

  // Off the road for several GPS fixes in a row (not renders): ask for a new route from here.
  const offCount = useRef(0)
  const lastReroute = useRef(0)
  useEffect(() => {
    offCount.current = 0 // a new route: start counting again
  }, [nav])
  useEffect(() => {
    if (simulating || !live || !nav) return
    const p = progress(nav, live, lastAlong.current)
    if (p.phase !== 'drive') return
    offCount.current = p.offRouteM > OFF_ROUTE_M ? offCount.current + 1 : 0
    if (
      offCount.current >= OFF_ROUTE_FIXES &&
      Date.now() - lastReroute.current > REROUTE_EVERY_MS
    ) {
      lastReroute.current = Date.now()
      offCount.current = 0
      setFrom(live)
    }
    // Runs once per GPS fix; `nav` is read, not a trigger.
  }, [live, simulating]) // eslint-disable-line react-hooks/exhaustive-deps
  const rerouting = !simulating && live !== null && (prog?.offRouteM ?? 0) > OFF_ROUTE_M

  // Text and voice for the current instruction.
  const node = route?.target.node_id ?? incident?.first_node_id
  const headline = !prog
    ? ''
    : prog.phase === 'arrived'
      ? t('guide.arrived', { node })
      : prog.phase === 'walk'
        ? t('guide.walk', { node })
        : prog.next
          ? instruction(prog.next, t)
          : ''
  const arrow: IconName = prog
    ? prog.phase === 'drive'
      ? ARROW[prog.next?.kind ?? 'straight']
      : ARROW[prog.phase]
    : 'straight'

  const [voice, setVoice] = useState(readVoice)
  const toggleVoice = () => {
    setVoice((v) => {
      try {
        localStorage.setItem(VOICE_KEY, v ? 'off' : 'on')
      } catch {
        // not remembered in private mode
      }
      if (v) window.speechSynthesis?.cancel()
      return !v
    })
  }
  const spoken = useRef(new Set<string>())
  useEffect(() => {
    if (!voice || !live || !prog || !headline || !('speechSynthesis' in window)) return
    const stepKey = `${prog.phase}:${prog.next?.location.join(',') ?? ''}`
    const near = prog.phase === 'drive' && prog.toNextM <= PREPARE_M
    const key = near ? `${stepKey}:near` : stepKey
    if (spoken.current.has(key)) return
    spoken.current.add(key)
    const text =
      prog.phase === 'drive'
        ? `${t('guide.in', { distance: formatDistance(prog.toNextM, lang) })}, ${headline}`
        : headline
    const u = new SpeechSynthesisUtterance(text)
    u.lang = SPEECH_LANG[lang] ?? lang
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }, [voice, live, prog, headline, lang, t])

  const [follow, setFollow] = useState(true)
  const stopFollowing = useCallback(() => setFollow(false), [])
  if (!incidents.isLoading && !incident) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-6 p-6 text-center">
        <p className="text-xl">{t('guide.gone')}</p>
        <button
          type="button"
          onClick={() => navigate('/crew')}
          className="min-h-14 rounded-lg bg-ink px-6 text-lg font-semibold text-white"
        >
          {t('guide.back')}
        </button>
      </div>
    )
  }

  const station = stations.find((s) => s.lon === route?.origin.lon && s.lat === route?.origin.lat)
  const canOnSite = incident ? crewActions(incident.status).includes('ON_SITE') : false
  // Only the road still ahead is drawn once the vehicle is moving.
  const ahead: [number, number][] =
    nav && prog && live
      ? [
          [live.lon, live.lat],
          ...nav.route.drive.geometry.filter((_, i) => nav.cum[i]! > prog.alongM),
        ]
      : (nav?.route.drive.geometry ?? [])
  const heading =
    nav && prog && live
      ? prog.phase === 'drive'
        ? headingAt(nav, prog.alongM)
        : headingTo(nav, live, nav.route.target)
      : 0

  return (
    <div className="flex h-full flex-col">
      <section
        aria-live="polite"
        className={`flex min-h-24 items-center gap-4 px-4 py-3 text-white ${
          prog?.phase === 'arrived' ? 'bg-ok' : 'bg-ink'
        }`}
      >
        {routeQuery.isError ? (
          <div className="flex w-full items-center justify-between gap-3">
            <p className="text-xl font-bold">{t('guide.error')}</p>
            <button
              type="button"
              onClick={() => void routeQuery.refetch()}
              className="min-h-12 rounded-lg bg-white px-4 font-bold text-ink"
            >
              {t('guide.retry')}
            </button>
          </div>
        ) : !prog ? (
          <p className="text-xl font-bold">{t('guide.loading')}</p>
        ) : (
          <>
            {/* Turn arrows never mirror in Arabic: left is left. */}
            <span
              dir="ltr"
              className="grid size-16 shrink-0 place-items-center rounded-lg bg-white/10"
            >
              <Icon name={arrow} size={44} strokeWidth={2.5} />
            </span>
            <div className="min-w-0">
              {prog.phase !== 'arrived' && (
                <p className="text-4xl font-bold tabular-nums">
                  {formatDistance(prog.toNextM, lang)}
                </p>
              )}
              <p className="text-xl font-semibold leading-tight">{headline}</p>
            </div>
          </>
        )}
      </section>
      {rerouting && (
        <p role="status" className="bg-alert-fill px-4 py-1.5 text-center font-semibold text-ink">
          {t('guide.rerouting')}
        </p>
      )}

      <div className="relative min-h-0 flex-1">
        {nav && (
          <DriveMap
            route={nav.route}
            ahead={ahead}
            position={live}
            heading={heading}
            follow={follow}
            updateMs={simulating ? DEMO_TICK_MS : GPS_UPDATE_MS}
            onUserMove={stopFollowing}
          />
        )}

        <div className="pointer-events-none absolute inset-x-0 top-0 z-[1000] flex flex-col items-center gap-2 p-3">
          {route && !live && !simulating && (
            <div className="pointer-events-auto flex max-w-sm flex-col items-center gap-3 rounded-lg border border-line-strong bg-surface p-4 text-center shadow-sm">
              <p className="text-sm text-ink-2">{t('guide.noGps')}</p>
              <button
                type="button"
                onClick={() => setSimStart(Date.now())}
                className="min-h-12 rounded-md bg-ink px-4 font-semibold text-white"
              >
                {t('guide.simulate')}
              </button>
            </div>
          )}
          {simulating && (
            <div className="pointer-events-auto flex items-center gap-3 rounded-full border border-line-strong bg-surface py-1 ps-3 pe-1 text-sm font-medium text-ink shadow-sm">
              <span
                aria-hidden
                className="eg-pulse inline-block size-2 rounded-full bg-alert-fill"
              />
              {t('guide.simulating')}
              <button
                type="button"
                onClick={() => {
                  setSimStart(null)
                  setSimPos(null)
                }}
                className="min-h-8 rounded-full bg-paper px-3 font-semibold"
              >
                {t('guide.stopSimulation')}
              </button>
            </div>
          )}
        </div>
        {!follow && live && (
          <button
            type="button"
            onClick={() => setFollow(true)}
            className="absolute start-4 bottom-4 z-[1000] flex min-h-12 items-center gap-2 rounded-full border border-line-strong bg-surface px-4 font-semibold text-ink shadow-sm"
          >
            <Icon name="locate" size={20} />
            {t('guide.recenter')}
          </button>
        )}
      </div>

      <footer className="flex flex-col gap-2 border-t border-line bg-surface p-3">
        {prog?.phase === 'arrived' && canOnSite && (
          <button
            type="button"
            onClick={() => {
              if (myCrew !== null)
                setStatus.mutate({ id: incidentId, status: 'ON_SITE', crewId: myCrew })
              navigate('/crew')
            }}
            className="min-h-16 rounded-lg bg-ember text-3xl font-bold text-white active:bg-ember-deep"
          >
            {t('guide.onSite')}
          </button>
        )}
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            {prog && prog.phase !== 'arrived' && (
              <>
                <p className="whitespace-nowrap text-2xl font-bold tabular-nums">
                  {Math.max(1, Math.round(prog.remainingS / 60))} min ·{' '}
                  {formatDistance(prog.remainingM, lang)}
                </p>
                <p className="text-sm font-medium text-ink-2">
                  {t('guide.eta')} {clock(prog.remainingS, lang)}
                </p>
              </>
            )}
            {route && (
              <p className="truncate text-sm text-ink-2">
                {route.origin.source === 'gps'
                  ? t('guide.fromGps')
                  : t('guide.fromStation', { station: station?.name ?? '' })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={toggleVoice}
            aria-pressed={voice}
            aria-label={voice ? t('guide.voiceOn') : t('guide.voiceOff')}
            className="grid size-14 shrink-0 place-items-center rounded-full border border-line-strong text-ink"
          >
            <Icon name={voice ? 'speaker' : 'speakerOff'} size={24} />
          </button>
          <button
            type="button"
            onClick={() => {
              window.speechSynthesis?.cancel()
              navigate('/crew')
            }}
            className="min-h-14 shrink-0 rounded-lg bg-ink px-5 text-lg font-semibold text-white"
          >
            {t('guide.exit')}
          </button>
        </div>
      </footer>
    </div>
  )
}
