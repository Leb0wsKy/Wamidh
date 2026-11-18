import { useTranslation } from 'react-i18next'
import type { AlertProposal, Incident } from '../api/types'
import { PopulationAlert } from './PopulationAlert'

interface Props {
  /** open incidents, most urgent first */
  incidents: Incident[]
  selectedId: number
  onSelect: (incidentId: number) => void
  proposal: AlertProposal | undefined
  onSend: () => void
  sending?: boolean
  error?: string | null
}

/** Residents tab: the open fires, and the public alert the dispatcher can broadcast for each. */
export function FireAlertPanel({
  incidents,
  selectedId,
  onSelect,
  proposal,
  onSend,
  sending,
  error,
}: Props) {
  const { t } = useTranslation()
  const selected = incidents.find((i) => i.id === selectedId)

  return (
    <div className="flex flex-col gap-4 px-4 pb-4">
      {incidents.length > 1 && (
        <div role="tablist" className="flex flex-wrap gap-2">
          {incidents.map((i) => (
            <button
              key={i.id}
              type="button"
              role="tab"
              aria-selected={i.id === selectedId}
              onClick={() => onSelect(i.id)}
              className={`min-h-10 rounded-md border px-3 text-sm font-medium ${
                i.id === selectedId
                  ? 'border-ember bg-ember-soft text-ink'
                  : 'border-line-strong bg-surface text-ink-2 hover:text-ink'
              }`}
            >
              {t('station.node')} {i.first_node_id} <span dir="ltr">#{i.id}</span>
            </button>
          ))}
        </div>
      )}
      {incidents.length === 1 && selected && (
        <p role="tablist" className="text-sm font-medium text-ink-2">
          <span role="tab" aria-selected="true">
            {t('station.node')} {selected.first_node_id} <span dir="ltr">#{selected.id}</span> ·{' '}
            {t(`incidentStatus.${selected.status}`)}
          </span>
        </p>
      )}
      {selected && (
        <PopulationAlert
          incident={selected}
          proposal={proposal}
          onSend={onSend}
          sending={sending}
          error={error}
        />
      )}
    </div>
  )
}
