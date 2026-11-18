// Wamidh's own line icons (24 px grid, 1.75 stroke, currentColor), so the interface does
// not depend on emoji, whose look changes with every phone and operating system.

export const PATHS = {
  flame:
    'M12 3c.4 3 4.6 4.9 4.6 9.6A4.6 4.6 0 0 1 7.4 12.6c0-2 1-3.4 2.1-4.2.2 1.7 1 2.6 2 2.6-.2-3 .1-5.4.5-8Z',
  sensor:
    'M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z M7.8 7.8a6 6 0 0 0 0 8.4 M16.2 7.8a6 6 0 0 1 0 8.4 M5 5a10 10 0 0 0 0 14 M19 5a10 10 0 0 1 0 14',
  gateway:
    'M12 10v11 M8 21h8 M9.5 21 12 10l2.5 11 M12 8.5a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z M8.8 4.6a4.5 4.5 0 0 0 0 5.8 M15.2 4.6a4.5 4.5 0 0 1 0 5.8',
  truck:
    'M2.5 6.5h11v10h-11Z M13.5 9.5h4.2l3.3 3.6v3.4h-7.5 M6.5 19a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Z M17 19a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Z',
  speaker: 'M4 9h3.5L12 5v14l-4.5-4H4Z M15.5 9a4.2 4.2 0 0 1 0 6 M18 6.5a8 8 0 0 1 0 11',
  speakerOff: 'M4 9h3.5L12 5v14l-4.5-4H4Z M16 9.5l5 5 M21 9.5l-5 5',
  locate:
    'M12 19a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z M12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M12 2v3 M12 19v3 M2 12h3 M19 12h3',
  walk: 'M13.5 6a1.7 1.7 0 1 0 0-3.4 1.7 1.7 0 0 0 0 3.4Z M10 21l2.2-6.2 2.8 3V21 M12.2 14.8l-1-5.3 3.8-1 2 3.2h2.5 M11.2 9.5 8 11.8V15',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  broadcast:
    'M12 13a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M12 13v8 M8.5 8a5 5 0 0 0 0 7 M15.5 8a5 5 0 0 1 0 7 M5.6 5a9 9 0 0 0 0 13 M18.4 5a9 9 0 0 1 0 13',
  people:
    'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M3.5 19.5a5.5 5.5 0 0 1 11 0 M16 11a2.5 2.5 0 1 0 0-5 M17.2 13.8a4.8 4.8 0 0 1 3.3 5.7',
  close: 'M6 6l12 12 M18 6 6 18',
  chevron: 'M6 9l6 6 6-6',
  battery: 'M3 8.5h15v7H3Z M18 10.5h2.5v3H18 M5.5 11v2',
  straight: 'M12 20V5 M6 11l6-6 6 6',
  slight_left: 'M15 20v-6.5L8 6.5 M8 12.5v-6h6',
  left: 'M19 20v-6a4 4 0 0 0-4-4H5 M10 5 5 10l5 5',
  slight_right: 'M9 20v-6.5l7-7 M10 6.5h6v6',
  right: 'M5 20v-6a4 4 0 0 1 4-4h10 M14 5l5 5-5 5',
  uturn: 'M16 20V9.5a4.5 4.5 0 0 0-9 0V14 M4 11l3 3 3-3',
  arrive: 'M6 21V4 M6 4.5h11l-2.2 4 2.2 4H6',
  siren: 'M7 18v-5a5 5 0 0 1 10 0v5 M5 18h14v2.5H5Z M12 3v2 M4.2 6.2l1.4 1.4 M19.8 6.2l-1.4 1.4',
} as const

export type IconName = keyof typeof PATHS

/** The same icon as an HTML string, for map markers built outside React. */
export function iconHtml(name: IconName, size = 20, filled = false): string {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="${
    filled ? 'currentColor' : 'none'
  }" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="${PATHS[name]}"/></svg>`
}
