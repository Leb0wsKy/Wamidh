import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useAlarm, type AudioLike } from './useAlarm'

function fakeAudio(initial: AudioContextState) {
  const started: number[] = []
  const stopped: number[] = []
  let n = 0
  const ctx = {
    state: initial,
    currentTime: 0,
    destination: {},
    started,
    stopped,
    async resume() {
      ctx.state = 'running'
    },
    createGain() {
      return { gain: { value: 0 }, connect: (d: unknown) => d } as unknown as GainNode
    },
    createOscillator() {
      const id = ++n
      return {
        type: 'sine',
        frequency: { setValueAtTime: () => {} },
        connect: (g: { connect: (d: unknown) => unknown }) => g,
        start: () => started.push(id),
        stop: () => stopped.push(id),
      } as unknown as OscillatorNode
    },
  }
  return ctx as typeof ctx & AudioLike
}

describe('useAlarm', () => {
  it('sounds by itself when a fire arrives and the browser allows audio', () => {
    const ctx = fakeAudio('running') // e.g. station PC in kiosk mode with autoplay allowed
    const { result, rerender } = renderHook(({ ringing }) => useAlarm(ringing, () => ctx), {
      initialProps: { ringing: false },
    })
    expect(ctx.started).toEqual([])

    rerender({ ringing: true })

    expect(ctx.started).toEqual([1])
    expect(result.current.soundLocked).toBe(false)
  })

  it('reports locked sound and starts on the first click anywhere', async () => {
    const ctx = fakeAudio('suspended')
    const { result } = renderHook(() => useAlarm(true, () => ctx))
    expect(result.current.soundLocked).toBe(true)
    expect(ctx.started).toEqual([])

    await act(async () => {
      document.dispatchEvent(new Event('pointerdown'))
    })

    expect(result.current.soundLocked).toBe(false)
    expect(ctx.started).toEqual([1])
  })

  it('stops when the incident is acknowledged', () => {
    const ctx = fakeAudio('running')
    const { rerender } = renderHook(({ ringing }) => useAlarm(ringing, () => ctx), {
      initialProps: { ringing: true },
    })

    rerender({ ringing: false })

    expect(ctx.stopped).toEqual([1])
  })

  it('chimes once for a fire spreading, only when sound is allowed', () => {
    const locked = fakeAudio('suspended')
    const a = renderHook(() => useAlarm(false, () => locked))
    act(() => a.result.current.chime())
    expect(locked.started).toEqual([])

    const open = fakeAudio('running')
    const b = renderHook(() => useAlarm(false, () => open))
    act(() => b.result.current.chime())
    expect(open.started).toEqual([1])
  })
})
