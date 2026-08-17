'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchAlerts,
  fetchFaceLogs,
  fetchCameras,
} from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  ConfidenceMeter,
  FaceTile,
  RoleBadge,
  SectionHeading,
  StatusBadge,
} from '@/components/dashboard/shared'
import { formatTime, statusLabel } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Alert, DetectionStatus } from '@/lib/types'
import {
  BellRing,
  Check,
  ChevronLeft,
  ChevronRight,
  ScanFace,
  Search,
  UserPlus,
  UserRoundPlus,
  Video,
  X,
} from 'lucide-react'

const PAGE_SIZE = 8

// --- Alert sidebar ---------------------------------------------------------

function AlertCard({
  alert,
  onAck,
}: {
  alert: Alert
  onAck: (id: string) => void
}) {
  const severityRing =
    alert.severity === 'critical'
      ? 'ring-destructive/40'
      : alert.severity === 'high'
        ? 'ring-warning/40'
        : 'ring-border'
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card/60 p-3 ring-1 ring-inset',
        severityRing,
        alert.acknowledged && 'opacity-55',
      )}
    >
      <div className="flex items-start gap-3">
        <div className="flex gap-1.5">
          <FaceTile tone={alert.snapshotTone} size="md" flagged label="ID" />
          <FaceTile tone="cyan" size="md" label="FRM" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-sm font-semibold">{alert.profileName}</p>
            <Badge
              className={cn(
                'rounded-md font-mono uppercase',
                alert.severity === 'critical'
                  ? 'bg-destructive/15 text-destructive'
                  : alert.severity === 'high'
                    ? 'bg-warning/15 text-warning'
                    : 'bg-muted text-muted-foreground',
              )}
            >
              {alert.severity}
            </Badge>
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
            {alert.reason}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
            <span>{alert.cameraId}</span>
            <span>{formatTime(alert.timestamp)}</span>
            <span className="text-foreground">{alert.confidence.toFixed(1)}%</span>
          </div>
        </div>
      </div>
      <div className="mt-2.5 flex items-center gap-2">
        <RoleBadge role={alert.role} />
        <Button
          size="xs"
          variant={alert.acknowledged ? 'ghost' : 'outline'}
          className="ml-auto"
          disabled={alert.acknowledged}
          onClick={() => onAck(alert.id)}
        >
          <Check /> {alert.acknowledged ? 'Acknowledged' : 'Acknowledge'}
        </Button>
      </div>
    </div>
  )
}

function AlertSidebar() {
  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => fetchAlerts(),
  })
  const [acked, setAcked] = useState<string[]>([])

  const merged = alerts.map((a) => ({
    ...a,
    acknowledged: a.acknowledged || acked.includes(a.id),
  }))
  const activeCount = merged.filter((a) => !a.acknowledged).length

  return (
    <Card className="h-full gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={BellRing}
          title="Priority Alerts"
          count={activeCount}
          description="Watchlist & blacklist hits requiring review"
        />
      </CardHeader>
      <CardContent className="flex max-h-[720px] flex-col gap-2.5 overflow-y-auto p-3">
        {merged.map((alert) => (
          <AlertCard
            key={alert.id}
            alert={alert}
            onAck={(id) => setAcked((prev) => [...prev, id])}
          />
        ))}
      </CardContent>
    </Card>
  )
}

// --- Live camera feeds ----------------------------------------------------

function CCTVTimestamp() {
  const [time, setTime] = useState(() => new Date())
  
  // Use useEffect to update the time every second (optional, safe for client components)
  // To avoid hydration mismatch, we render the time only after mount if needed, 
  // or just use suppressHydrationWarning.
  return <span suppressHydrationWarning>{time.toISOString().split('T')[1].substring(0, 8)} Z</span>
}

function LiveCameraFeeds() {
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => fetchCameras(),
  })
  
  const onlineCameras = cameras.filter(c => c.status === 'online' || c.status === 'degraded')

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Video}
          title="Live Camera Feeds"
          count={onlineCameras.length}
          description="Real-time CCTV monitoring streams"
        />
      </CardHeader>
      <CardContent className="p-3">
        {onlineCameras.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            No online cameras available.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-2">
            {onlineCameras.map((c) => (
              <div
                key={c.id}
                className="group relative overflow-hidden rounded-lg border border-border bg-card/50 aspect-video shadow-inner"
              >
                {/* Simulated CCTV feed image */}
                <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1557597774-9d273605dfa9?w=800&q=80')] bg-cover bg-center opacity-40 grayscale group-hover:grayscale-0 transition-all duration-700" />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/40 mix-blend-multiply" />
                {/* Scanlines overlay */}
                <div className="absolute inset-0 pointer-events-none opacity-20 bg-[linear-gradient(rgba(255,255,255,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_4px,3px_100%]" />
                
                {/* CCTV Overlays */}
                <div className="absolute top-3 left-3 flex items-center gap-2 font-mono text-[10px] sm:text-xs font-semibold text-white/90 drop-shadow-md">
                  <div className="flex items-center gap-1.5 rounded-sm bg-black/60 px-2 py-0.5 border border-white/10">
                    <div className="size-2 rounded-full bg-red-500 animate-pulse" />
                    REC
                  </div>
                  <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10">
                    {c.name}
                  </div>
                </div>
                
                <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between font-mono text-[10px] sm:text-xs text-white/80 drop-shadow-md">
                  <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10 truncate max-w-[60%]">
                    IP: {c.ipAddress || '192.168.1.x'} | {c.zone || 'General'}
                  </div>
                  <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10">
                    <CCTVTimestamp />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// --- Log data table --------------------------------------------------------

const STATUS_FILTERS: Array<'all' | DetectionStatus> = [
  'all',
  'recognized',
  'flagged',
  'unknown',
]

function LogTable() {
  const { data: logs = [] } = useQuery({
    queryKey: ['face-logs'],
    queryFn: () => fetchFaceLogs(),
  })
  const [status, setStatus] = useState<'all' | DetectionStatus>('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)

  const filtered = useMemo(() => {
    return logs.filter((l) => {
      if (status !== 'all' && l.status !== status) return false
      if (query) {
        const q = query.toLowerCase()
        return (
          l.id.toLowerCase().includes(q) ||
          l.cameraName.toLowerCase().includes(q) ||
          l.cameraId.toLowerCase().includes(q) ||
          (l.profileName?.toLowerCase().includes(q) ?? false)
        )
      }
      return true
    })
  }, [logs, status, query])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const current = Math.min(page, pageCount - 1)
  const rows = filtered.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Search}
          title="Detection Event Log"
          count={filtered.length}
          description="Immutable, paginated trail of every detection event"
          action={
            <div className="flex items-center gap-1.5">
              <div className="relative">
                <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value)
                    setPage(0)
                  }}
                  placeholder="Search ID / camera / subject"
                  className="h-8 w-56 pl-7 text-xs"
                />
              </div>
            </div>
          }
        />
        <div className="mt-3 flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((s) => (
            <Button
              key={s}
              size="xs"
              variant={status === s ? 'secondary' : 'ghost'}
              className={cn('capitalize', status === s && 'ring-1 ring-inset ring-border')}
              onClick={() => {
                setStatus(s)
                setPage(0)
              }}
            >
              {s === 'all' ? 'All Events' : statusLabel[s]}
            </Button>
          ))}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Snapshot</TableHead>
              <TableHead>Event ID</TableHead>
              <TableHead>Subject</TableHead>
              <TableHead>Camera</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Liveness</TableHead>
              <TableHead className="pr-4">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((l) => (
              <TableRow key={l.id}>
                <TableCell className="pl-4">
                  <FaceTile
                    tone={l.snapshotTone}
                    size="sm"
                    flagged={l.status === 'flagged'}
                  />
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {l.id}
                </TableCell>
                <TableCell>
                  <span className="text-sm">
                    {l.profileName ?? (
                      <span className="text-muted-foreground">Unidentified</span>
                    )}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  <span className="font-mono text-xs">{l.cameraId}</span>{' '}
                  {l.cameraName}
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                  {formatTime(l.timestamp)}
                </TableCell>
                <TableCell>
                  <ConfidenceMeter value={l.confidence} />
                </TableCell>
                <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                  {l.livenessScore}
                </TableCell>
                <TableCell className="pr-4">
                  <StatusBadge status={l.status} />
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                  No events match the current filters.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
      <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
        <p className="font-mono text-xs text-muted-foreground">
          Page {current + 1} / {pageCount} · {filtered.length} events
        </p>
        <div className="flex gap-1.5">
          <Button
            size="icon-sm"
            variant="outline"
            disabled={current === 0}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
          >
            <ChevronLeft />
          </Button>
          <Button
            size="icon-sm"
            variant="outline"
            disabled={current >= pageCount - 1}
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
    </Card>
  )
}

export function AlertsTab() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-4">
        <LiveCameraFeeds />
        <LogTable />
      </div>
      <AlertSidebar />
    </div>
  )
}
