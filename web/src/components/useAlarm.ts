import { useCallback, useEffect, useRef, useState } from 'react'

/** The part of AudioContext the alarm uses (injectable for tests). */
export type AudioLike = Pick<
  AudioContext,
  'state' | 'currentTime' | 'destination' | 'resume' | 'createGain' | 'createOscillator'
>

const defaultAudio = (): AudioLike => new AudioContext()

/**
 * Station alarm. It starts BY ITSELF whenever `ringing` is true (an unacknowledged fire).
 *
 * Browsers only let a page play sound after a user interaction, or when the browser is
 * started with autoplay allowed (station PC: Edge/Chrome with
 * --autoplay-policy=no-user-gesture-required, see scripts/station-kiosk.ps1). So: sound is
 * unlocked by any click or key press anywhere on the page, and `soundLocked` tells the UI to
 * say so. The two-tone siren is generated with Web Audio: nothing to download or cache.
 */
export function useAlarm(ringing: boolean, createAudio: () => AudioLike = defaultAudio) {
  const ctxRef = useRef<AudioLike | null>(null)
  const [unlocked, setUnlocked] = useState(false)

  useEffect(() => {
    const ctx = createAudio()
    ctxRef.current = ctx
    const refresh = () => setUnlocked(ctx.state === 'running')
    refresh()
    const unlock = () => {
      void ctx.resume().then(refresh)
    }
    document.addEventListener('pointerdown', unlock)
    document.addEventListener('keydown', unlock)
    return () => {
      document.removeEventListener('pointerdown', unlock)
      document.removeEventListener('keydown', unlock)
    }
  }, [createAudio])

  useEffect(() => {
    const ctx = ctxRef.current
    if (!ringing || !unlocked || !ctx) return
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    gain.gain.value = 0.25
    osc.type = 'square'
    osc.connect(gain).connect(ctx.destination)
    const t0 = ctx.currentTime
    for (let i = 0; i < 1200; i++) osc.frequency.setValueAtTime(i % 2 ? 660 : 880, t0 + i * 0.5)
    osc.start()
    return () => osc.stop()
  }, [ringing, unlocked])

  /** Three short beeps: attention without the full siren (e.g. a fire spreading). */
  const chime = useCallback(() => {
    const ctx = ctxRef.current
    if (!unlocked || !ctx) return
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    gain.gain.value = 0.3
    osc.type = 'sine'
    osc.connect(gain).connect(ctx.destination)
    const t0 = ctx.currentTime
    for (let i = 0; i < 6; i++) osc.frequency.setValueAtTime(i % 2 ? 0 : 1175, t0 + i * 0.18)
    osc.start()
    osc.stop(t0 + 1.1)
  }, [unlocked])

  return { soundLocked: !unlocked, chime }
}
