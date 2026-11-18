import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isOpen } from '../domain/incident'
import { useApi } from './context'
import type { IncidentStatus } from './types'

export function useNodes() {
  const { api } = useApi()
  return useQuery({ queryKey: ['nodes'], queryFn: () => api.listNodes() })
}

export function useGateways() {
  const { api } = useApi()
  return useQuery({ queryKey: ['gateways'], queryFn: () => api.listGateways() })
}

export function useRiskOverlay() {
  const { api } = useApi()
  return useQuery({ queryKey: ['risk'], queryFn: () => api.riskOverlay() })
}

/** Every incident, closed ones included (the history), newest first. Shares the "incidents"
 *  key prefix, so every mutation that refreshes the open list refreshes this one too. */
export function useAllIncidents() {
  const { api } = useApi()
  return useQuery({
    queryKey: ['incidents', 'all'],
    queryFn: async () => (await api.listIncidents()).sort((a, b) => b.id - a.id),
  })
}

/** Open incidents, newest first. */
/** Recent readings of the sensors on screen; refreshed in the background for the trends. */
export function useHistory(minutes: number, refreshMs: number, nodeIds: number[]) {
  const { api } = useApi()
  return useQuery({
    queryKey: ['history', minutes, nodeIds.join(',')],
    queryFn: () => api.history(minutes, nodeIds),
    refetchInterval: refreshMs,
    enabled: nodeIds.length > 0,
    placeholderData: (previous) => previous, // keep the old trends while a search narrows
  })
}

export function useOpenIncidents() {
  const { api } = useApi()
  return useQuery({
    queryKey: ['incidents'],
    queryFn: async () =>
      (await api.listIncidents()).filter((i) => isOpen(i.status)).sort((a, b) => b.id - a.id),
  })
}

export function useAcknowledge() {
  const { api } = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.acknowledge(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ['incidents'] }),
  })
}

export function useSetStatus() {
  const { api } = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, status, crewId }: { id: number; status: IncidentStatus; crewId: number }) =>
      api.setStatus(id, status, crewId),
    onSuccess: () => client.invalidateQueries({ queryKey: ['incidents'] }),
  })
}

export function useAssign() {
  const { api } = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, crewId }: { id: number; crewId: number }) => api.assign(id, crewId),
    onSettled: () => client.invalidateQueries({ queryKey: ['incidents'] }),
  })
}

export function useCrews() {
  const { api } = useApi()
  return useQuery({ queryKey: ['crews'], queryFn: () => api.listCrews() })
}

export function useStations() {
  const { api } = useApi()
  return useQuery({ queryKey: ['stations'], queryFn: () => api.listStations() })
}

/** Crew id -> display name. */
export function useCrewName(): (crewId: number) => string {
  const crews = useCrews().data ?? []
  return (id) => crews.find((c) => c.id === id)?.name ?? `#${id}`
}

// --- population alerts (ADR 0003) ---------------------------------------------------------

export function useZones() {
  const { api } = useApi()
  return useQuery({ queryKey: ['zones'], queryFn: () => api.listZones(), staleTime: Infinity })
}

export function useTowers() {
  const { api } = useApi()
  return useQuery({ queryKey: ['towers'], queryFn: () => api.listTowers(), staleTime: Infinity })
}

/** Who a public alert for this incident would reach (refreshed with the incident). */
export function useAlertProposal(incidentId: number | null) {
  const { api } = useApi()
  return useQuery({
    queryKey: ['incidents', 'proposal', incidentId],
    queryFn: () => api.alertProposal(incidentId as number),
    enabled: incidentId !== null,
  })
}

/** Public alerts, newest first; polled because residents' pages have no live socket need. */
export function usePublicAlerts(activeOnly: boolean, refreshMs = 15_000) {
  const { api } = useApi()
  return useQuery({
    queryKey: ['alerts', activeOnly],
    queryFn: () => api.listAlerts(activeOnly),
    refetchInterval: refreshMs,
  })
}

export function useSendAlert() {
  const { api } = useApi()
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, confirmedBy }: { id: number; confirmedBy: string }) =>
      api.sendAlert(id, confirmedBy),
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['incidents'] }),
        client.invalidateQueries({ queryKey: ['alerts'] }),
      ]),
  })
}

// --- fire spread forecast (ADR 0004) ------------------------------------------------------

/** The spread forecast of an incident; refreshed when the backend announces a new one. */
export function useForecast(incidentId: number | null) {
  const { api } = useApi()
  return useQuery({
    queryKey: ['forecast', incidentId],
    queryFn: () => api.forecast(incidentId as number),
    enabled: incidentId !== null,
    placeholderData: (previous) => previous, // no blank map between two updates
    retry: 1,
  })
}
