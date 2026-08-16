'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchKpis } from '@/lib/api'
import { formatNumber, healthLabel } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  Camera as CameraIcon,
  ScanFace,
  ShieldAlert,
  Activity,
} from 'lucide-react'
import type { SystemHealth } from '@/lib/types'

function HealthDot({ health }: { health: SystemHealth }) {
  const styles: Record<SystemHealth, string> = {
    green: 'bg-success shadow-[0_0_0_3px_var(--success)]/20',
    yellow: 'bg-warning',
    red: 'bg-destructive',
  }
  return (
    <span className="relative flex size-2.5">
      {health !== 'green' && (
        <span
          className={cn(
            'absolute inline-flex size-full animate-ping rounded-full opacity-60',
            health === 'red' ? 'bg-destructive' : 'bg-warning',
          )}
        />
      )}
      <span className={cn('relative inline-flex size-2.5 rounded-full', styles[health])} />
    </span>
  )
}

function Kpi({
  icon: Icon,
  label,
  value,
  tone,
  badge,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string
  tone?: string
  badge?: number
}) {
  return (
    <div className="flex items-center gap-3 px-4">
      <span
        className={cn(
          'relative flex size-9 items-center justify-center rounded-md bg-muted text-muted-foreground',
          tone,
        )}
      >
        <Icon className="size-4.5" />
        {badge ? (
          <span className="absolute -right-1.5 -top-1.5 flex min-w-4.5 items-center justify-center rounded-full bg-destructive px-1 py-0.5 font-mono text-[10px] font-bold leading-none text-destructive-foreground ring-2 ring-background">
            {badge}
          </span>
        ) : null}
      </span>
      <div className="leading-tight">
        <p className="font-mono text-lg font-semibold tabular-nums tracking-tight">
          {value}
        </p>
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
      </div>
    </div>
  )
}

export function TopNav() {
  const { data: kpis } = useQuery({ queryKey: ['kpis'], queryFn: () => fetchKpis() })

  const health: SystemHealth =
    kpis?.systemHealth === 'green' || kpis?.systemHealth === 'yellow' || kpis?.systemHealth === 'red'
      ? kpis.systemHealth
      : 'green'
  const connectedCameras =
    typeof kpis?.connectedCameras === 'number' ? kpis.connectedCameras : null
  const totalCameras = typeof kpis?.totalCameras === 'number' ? kpis.totalCameras : null
  const detectionsToday =
    typeof kpis?.detectionsToday === 'number' ? kpis.detectionsToday : null
  const activeAlerts = typeof kpis?.activeAlerts === 'number' ? kpis.activeAlerts : null

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="flex flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center lg:justify-between lg:px-6">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-md bg-destructive/15 text-destructive ring-1 ring-inset ring-destructive/30">
            <ScanFace className="size-5" />
          </span>
          <div className="leading-tight">
            <p className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              SENTINEL
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] font-normal text-muted-foreground">
                FR-OPS v2.4
              </span>
            </p>
            <p className="text-[11px] text-muted-foreground">
              Facial Recognition Operations Console
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center divide-x divide-border rounded-lg border border-border bg-card/60 py-1.5">
          <Kpi
            icon={CameraIcon}
            label="Cameras Online"
            value={
              connectedCameras !== null && totalCameras !== null
                ? `${connectedCameras}/${totalCameras}`
                : '—/—'
            }
          />
          <Kpi
            icon={ScanFace}
            label="Detections Today"
            value={formatNumber(detectionsToday)}
          />
          <Kpi
            icon={ShieldAlert}
            label="Active Alerts"
            value={activeAlerts !== null ? String(activeAlerts) : '—'}
            badge={activeAlerts ?? undefined}
            tone="text-destructive"
          />
          <div className="flex items-center gap-3 px-4">
            <span className="flex size-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
              <Activity className="size-4.5" />
            </span>
            <div className="leading-tight">
              <p className="flex items-center gap-2 text-sm font-semibold">
                <HealthDot health={health} />
                {healthLabel[health]}
              </p>
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
                System Health
              </p>
            </div>
          </div>
        </div>
      </div>
    </header>
  )
}
