import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { initials, roleLabel, statusLabel, toneGradient } from '@/lib/format'
import type { DetectionStatus, ProfileRole } from '@/lib/types'
import { Scan } from 'lucide-react'

/**
 * Synthetic "face crop" tile. Rather than rendering real biometric imagery,
 * we draw a stylised camera frame (gradient + scanlines + corner brackets)
 * with the subject initials — enough to read as a snapshot in the UI.
 */
export function FaceTile({
  tone,
  label,
  size = 'md',
  className,
  flagged,
}: {
  tone: string
  label?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  flagged?: boolean
}) {
  const sizes = {
    sm: 'size-10 text-[10px]',
    md: 'size-14 text-xs',
    lg: 'size-20 text-sm',
    xl: 'h-32 w-full text-base',
  }
  return (
    <div
      className={cn(
        'relative flex shrink-0 items-center justify-center overflow-hidden rounded-md bg-gradient-to-br ring-1 ring-inset ring-border',
        toneGradient[tone] ?? toneGradient.sky,
        sizes[size],
        flagged && 'ring-2 ring-destructive/70',
        className,
      )}
      aria-hidden
    >
      <div className="scanlines absolute inset-0 opacity-60" />
      <span className="absolute left-1 top-1 size-1.5 border-l border-t border-foreground/50" />
      <span className="absolute right-1 top-1 size-1.5 border-r border-t border-foreground/50" />
      <span className="absolute bottom-1 left-1 size-1.5 border-b border-l border-foreground/50" />
      <span className="absolute bottom-1 right-1 size-1.5 border-b border-r border-foreground/50" />
      {label ? (
        <span className="font-mono font-semibold tracking-wider text-foreground/90">
          {label}
        </span>
      ) : (
        <Scan className="size-1/3 text-foreground/50" />
      )}
    </div>
  )
}

export function StatusBadge({ status }: { status: DetectionStatus }) {
  const styles: Record<DetectionStatus, string> = {
    recognized:
      'bg-success/15 text-success ring-1 ring-inset ring-success/25',
    flagged:
      'bg-destructive/15 text-destructive ring-1 ring-inset ring-destructive/25',
    unknown: 'bg-warning/15 text-warning ring-1 ring-inset ring-warning/25',
  }
  return (
    <Badge className={cn('rounded-md font-mono uppercase', styles[status])}>
      {statusLabel[status]}
    </Badge>
  )
}

export function RoleBadge({ role }: { role: ProfileRole }) {
  const styles: Record<ProfileRole, string> = {
    employee: 'bg-secondary text-secondary-foreground ring-1 ring-inset ring-border',
    vip: 'bg-info/15 text-info ring-1 ring-inset ring-info/25',
    visitor: 'bg-muted text-muted-foreground ring-1 ring-inset ring-border',
    watchlist: 'bg-warning/15 text-warning ring-1 ring-inset ring-warning/25',
    blacklist: 'bg-destructive/15 text-destructive ring-1 ring-inset ring-destructive/25',
  }
  return (
    <Badge className={cn('rounded-md', styles[role])}>{roleLabel[role]}</Badge>
  )
}

export function ConfidenceMeter({ value }: { value: number }) {
  const tone =
    value >= 85 ? 'bg-success' : value >= 60 ? 'bg-warning' : 'bg-destructive'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full', tone)} style={{ width: `${value}%` }} />
      </div>
      <span className="font-mono text-xs tabular-nums text-muted-foreground">
        {value.toFixed(1)}%
      </span>
    </div>
  )
}

export function SectionHeading({
  title,
  count,
  description,
  icon: Icon,
  action,
}: {
  title: string
  count?: number
  description?: string
  icon?: React.ComponentType<{ className?: string }>
  action?: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex items-start gap-2.5">
        {Icon ? (
          <span className="mt-0.5 flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon className="size-4" />
          </span>
        ) : null}
        <div>
          <h2 className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            {title}
            {typeof count === 'number' ? (
              <span className="font-mono text-xs font-normal text-muted-foreground">
                {count}
              </span>
            ) : null}
          </h2>
          {description ? (
            <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </div>
      {action}
    </div>
  )
}

export { initials }
