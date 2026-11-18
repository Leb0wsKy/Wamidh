/** Timestamps are stored in UTC and shown in Tunisian time (CLAUDE.md section 4). */
export function formatTime(iso: string, lng: string): string {
  return new Intl.DateTimeFormat(lng === 'ar' ? 'ar-TN' : lng, {
    timeZone: 'Africa/Tunis',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23', // 24-hour clock in every language
  }).format(new Date(iso))
}

/** "05/10 13:02": day/month and time in Tunisian time, for events that may be days old.
 *  Same numeric layout and Western digits in every language, like the rest of the UI. */
export function formatDateTime(iso: string): string {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Africa/Tunis',
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(iso))
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('day')}/${get('month')} ${get('hour')}:${get('minute')}`
}

/** "13:09": hours and minutes in Tunisian time, Western digits in every language. */
export function formatClock(iso: string): string {
  return formatDateTime(iso).split(' ')[1] ?? ''
}

/** A count with the language's thousands separator; ar-TN keeps Western digits. */
export function formatCount(n: number, lng: string): string {
  return new Intl.NumberFormat(lng === 'ar' ? 'ar-TN' : lng).format(n)
}
