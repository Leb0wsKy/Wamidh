import { createContext, useContext } from 'react'
import type { EmberApi } from './types'

export interface ApiContextValue {
  api: EmberApi
  /** true while the live event stream from the backend is connected */
  connected: boolean
}

export const ApiContext = createContext<ApiContextValue | null>(null)

export function useApi(): ApiContextValue {
  const ctx = useContext(ApiContext)
  if (!ctx) throw new Error('useApi must be used inside <ApiProvider>')
  return ctx
}
