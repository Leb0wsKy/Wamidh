import { useTranslation } from 'react-i18next'
import type { PublicAlert } from '../api/types'
import { formatClock } from '../domain/time'
import { Icon } from './Icon'

/** A public alert as a resident's phone shows it: Arabic, full text. */
export function PhoneAlertCard({ alert }: { alert: PublicAlert }) {
  const { t } = useTranslation()
  const [headline, ...body] = alert.message_ar.split('\n')

  return (
    <article className="overflow-hidden rounded-2xl border border-line-strong bg-surface shadow-[0_2px_8px_rgb(26_26_25/0.08)]">
      <header className="flex items-center gap-2 bg-ember px-3.5 py-2 text-white">
        <Icon name="broadcast" size={16} />
        <span className="text-sm font-semibold">{t('residents.emergencyAlert')}</span>
        <time dateTime={alert.created_at} className="ms-auto text-sm tabular-nums" dir="ltr">
          {formatClock(alert.created_at)}
        </time>
      </header>
      <div lang="ar" dir="rtl" className="space-y-1 px-4 py-3 leading-relaxed">
        <p className="font-semibold">{headline}</p>
        {body.map((line, i) => (
          <p key={i}>{line}</p>
        ))}
      </div>
    </article>
  )
}
