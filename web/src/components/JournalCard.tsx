import { useTranslation } from 'react-i18next'
import type { Incident } from '../api/types'
import { eventText } from '../domain/events'
import { formatDateTime } from '../domain/time'
import { recentEvents } from '../domain/watch'
import { Card } from './Card'

const FIRE_EVENTS = new Set(['node_fire', 'fire_spread', 'node_lost'])

interface Props {
  /** every incident, closed ones included */
  incidents: Incident[]
  limit?: number
  crewName?: (crewId: number) => string
}

/** The station's journal: the latest audit-log entries of every incident, newest first. */
export function JournalCard({ incidents, limit = 8, crewName = (id) => `#${id}` }: Props) {
  const { t } = useTranslation()
  const recent = recentEvents(incidents, limit)

  return (
    <Card title={t('journal.title')} className="pb-3">
      {recent.length === 0 ? (
        <p className="px-4 text-sm text-ink-2">{t('journal.empty')}</p>
      ) : (
        <ol className="mx-4 flex flex-col">
          {recent.map(({ incident, event }, i) => (
            <li
              key={`${incident.id}-${event.ts}-${event.type}-${i}`}
              className="flex items-baseline gap-3 border-b border-line py-1.5 text-sm last:border-b-0"
            >
              <time dateTime={event.ts} className="shrink-0 text-ink-2 tabular-nums" dir="ltr">
                {formatDateTime(event.ts)}
              </time>
              <span className={FIRE_EVENTS.has(event.type) ? 'text-ember' : 'text-ink'}>
                {eventText(event, t, crewName)}
              </span>
              <span dir="ltr" className="ms-auto shrink-0 text-ink-3 tabular-nums">
                #{incident.id}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}
