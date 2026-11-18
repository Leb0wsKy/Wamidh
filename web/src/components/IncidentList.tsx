import { useTranslation } from 'react-i18next'
import type { Incident } from '../api/types'
import { awaitingStation, endedAt, isOpen } from '../domain/incident'
import { formatElapsed } from '../domain/status'
import { Icon } from './Icon'

interface Props {
  /** in dispatch order: burning first, then under control */
  incidents: Incident[]
  selectedId: number | null
  onSelect: (incidentId: number) => void
  crewName: (crewId: number) => string
  now: number
}

export function IncidentList({ incidents, selectedId, onSelect, crewName, now }: Props) {
  const { t } = useTranslation()
  const groups = [
    {
      key: 'live',
      items: incidents.filter((i) => isOpen(i.status) && i.status !== 'UNDER_CONTROL'),
    },
    { key: 'settled', items: incidents.filter((i) => i.status === 'UNDER_CONTROL') },
    { key: 'closed', items: incidents.filter((i) => !isOpen(i.status)) },
  ].filter((g) => g.items.length > 0)

  return (
    <div className="flex flex-col gap-5">
      {groups.map((g) => (
        <section key={g.key} aria-label={t(`incidents.${g.key}`)}>
          <h2 className="eg-label mb-2">{t(`incidents.${g.key}`)}</h2>
          <ul className="flex flex-col gap-1.5">
            {g.items.map((i) => {
              const settled = g.key !== 'live' // under control or closed: quiet, grey
              const urgent = awaitingStation(i)
              const selected = i.id === selectedId
              return (
                <li key={i.id}>
                  <button
                    type="button"
                    aria-current={selected || undefined}
                    onClick={() => onSelect(i.id)}
                    className={`flex w-full flex-col gap-0.5 rounded-md border bg-surface px-3 py-2.5 text-start ${
                      selected ? 'border-ink shadow-sm' : 'border-line hover:border-line-strong'
                    } ${settled ? 'opacity-70' : ''} ${urgent ? 'border-s-4 border-s-ember' : ''}`}
                  >
                    <span className="flex items-center gap-2">
                      <Icon
                        name={i.status === 'FALSE_ALARM' ? 'close' : settled ? 'check' : 'flame'}
                        size={16}
                        filled={!settled}
                        className={
                          i.status === 'FALSE_ALARM'
                            ? 'text-ink-2'
                            : settled
                              ? 'text-ok'
                              : 'text-ember'
                        }
                      />
                      <span className="font-semibold text-ink">
                        {t('station.node')} {i.node_ids.join(', ')}
                      </span>
                      <span dir="ltr" className="text-sm text-ink-2">
                        #{i.id}
                      </span>
                      <span className="ms-auto text-sm text-ink-2 tabular-nums">
                        {formatElapsed((endedAt(i) ?? now) - Date.parse(i.created_at))}
                      </span>
                    </span>
                    <span className="flex items-center gap-2 ps-6 text-sm">
                      <span className={urgent ? 'font-semibold text-ember' : 'text-ink-2'}>
                        {t(`incidentStatus.${i.status}`)}
                      </span>
                      {i.assigned_crew != null && (
                        <span className="text-ink-2">· {crewName(i.assigned_crew)}</span>
                      )}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        </section>
      ))}
    </div>
  )
}
