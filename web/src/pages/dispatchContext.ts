import { useOutletContext } from 'react-router-dom'
import type { Spread } from '../domain/incident'

/** What the dispatcher's tabs share with DispatchLayout: siren state and the latest spread. */
export interface DispatchContext {
  soundLocked: boolean
  spread: Spread | null
}

export function useDispatch(): DispatchContext {
  return useOutletContext<DispatchContext>()
}
