// State that belongs to the crew's phone rather than to the backend.
import { useEffect, useState } from 'react'
import type { LonLat } from '../api/types'

const CREW_KEY = 'wamidh.crew'

/** The phone's position, if the crew member allows it. */
export function usePosition(maximumAgeMs = 30_000): LonLat | null {
  const [pos, setPos] = useState<LonLat | null>(null)
  useEffect(() => {
    if (!('geolocation' in navigator)) return
    const id = navigator.geolocation.watchPosition(
      (p) => setPos({ lat: p.coords.latitude, lon: p.coords.longitude }),
      () => setPos(null),
      { enableHighAccuracy: true, maximumAge: maximumAgeMs },
    )
    return () => navigator.geolocation.clearWatch(id)
  }, [maximumAgeMs])
  return pos
}

/** Which crew this phone belongs to (remembered on the device). */
export function useMyCrew(): [number | null, (id: number | null) => void] {
  const [crew, setCrew] = useState<number | null>(() => {
    try {
      const v = localStorage.getItem(CREW_KEY)
      return v ? Number(v) : null
    } catch {
      return null
    }
  })
  const update = (id: number | null) => {
    setCrew(id)
    try {
      if (id === null) localStorage.removeItem(CREW_KEY)
      else localStorage.setItem(CREW_KEY, String(id))
    } catch {
      // private mode: the choice is simply not remembered
    }
  }
  return [crew, update]
}
