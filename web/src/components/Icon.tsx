import { PATHS, type IconName } from './iconPaths'

export type { IconName }

interface Props {
  name: IconName
  size?: number
  className?: string
  /** filled glyph (flame on the fire marker) instead of an outline */
  filled?: boolean
  strokeWidth?: number
}

export function Icon({ name, size = 20, className, filled = false, strokeWidth = 1.75 }: Props) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
