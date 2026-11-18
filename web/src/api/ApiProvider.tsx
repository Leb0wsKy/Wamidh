import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { mergeIncident, upsertIncident } from '../domain/incident'
import { ApiContext } from './context'
import { HttpApi } from './http'
import type { EmberApi, Incident, SensorNode } from './types'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })

function createApi(): EmberApi {
  const wsScheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return new HttpApi({ base: '/api/v1', wsUrl: `${wsScheme}://${location.host}/api/v1/ws` })
}

/** Apply every live event to the cached lists at once; refetch everything after a reconnect. */
function LiveUpdates({ api }: { api: EmberApi }) {
  const client = useQueryClient()
  useEffect(
    () =>
      api.subscribe((e) => {
        if (e.kind === 'node') {
          client.setQueryData<SensorNode[]>(['nodes'], (old = []) => {
            const others = old.filter((n) => n.id !== e.node.id)
            const prev = old.find((n) => n.id === e.node.id)
            return [...others, { ...prev, ...e.node }].sort((a, b) => a.id - b.id)
          })
        } else if (e.kind === 'forecast') {
          void client.invalidateQueries({ queryKey: ['forecast', e.incident_id] })
        } else {
          client.setQueryData<Incident[]>(['incidents'], (old = []) =>
            mergeIncident(old, e.incident),
          )
          client.setQueryData<Incident[]>(['incidents', 'all'], (old) =>
            old ? upsertIncident(old, e.incident) : old,
          )
        }
      }),
    [api, client],
  )
  useEffect(
    () =>
      api.onConnection((up) => {
        if (up) void client.invalidateQueries()
      }),
    [api, client],
  )
  return null
}

export function ApiProvider({ children }: { children: ReactNode }) {
  const api = useMemo(() => createApi(), [])
  const [connected, setConnected] = useState(false)
  useEffect(() => api.onConnection(setConnected), [api])

  return (
    <ApiContext.Provider value={{ api, connected }}>
      <QueryClientProvider client={queryClient}>
        <LiveUpdates api={api} />
        {children}
      </QueryClientProvider>
    </ApiContext.Provider>
  )
}
