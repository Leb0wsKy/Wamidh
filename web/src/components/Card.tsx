import type { ReactNode } from 'react'

/** A box on the station page: white, thin border, optional small-caps title. */
export function Card({
  title,
  className = '',
  children,
}: {
  title?: string
  className?: string
  children: ReactNode
}) {
  return (
    <section
      aria-label={title}
      className={`flex flex-col rounded-lg border border-line bg-surface shadow-[0_1px_2px_rgb(26_26_25/0.04)] ${className}`}
    >
      {title && <h2 className="eg-label px-4 pt-3.5 pb-2">{title}</h2>}
      {children}
    </section>
  )
}
