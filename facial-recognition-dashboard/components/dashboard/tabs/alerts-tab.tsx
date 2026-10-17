'use client'

import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  acknowledgeAlert,
  fetchAlerts,
  fetchFaceLogs,
  fetchCameraEpisodes,
  fetchCameras,
  getCameraStreamUrl,
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
import { formatTime, formatDateTime, statusLabel } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Alert, DetectionStatus, CameraEpisode } from '@/lib/types'
import { useDashboardMode } from '@/lib/mode-context'
import {
  BellRing,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Compass,
  Footprints,
  Layers,
  LogIn,
  LogOut,
  Maximize2,
  Minimize2,
  ScanFace,
  Search,
  SlidersHorizontal,
  Sparkles,
  ArrowRight,
  ArrowUpDown,
  UserPlus,
  UserRoundPlus,
  Video,
  Workflow,
  X,
} from 'lucide-react'
import { LineageDrawer } from '@/components/dashboard/lineage-drawer'

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
            <span>{formatTime(alert.timestamp)} IST</span>
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
  const { mode, selectedBatchId } = useDashboardMode()
  const queryClient = useQueryClient()
  const { data: alerts = [] } = useQuery({
    queryKey: ['alerts', mode, selectedBatchId],
    queryFn: () => fetchAlerts(50, mode, selectedBatchId ?? undefined),
  })
  const [ackedLocal, setAckedLocal] = useState<string[]>([])

  const ackMutation = useMutation({
    mutationFn: ({ id, ack }: { id: string; ack: boolean }) => acknowledgeAlert(id, ack),
    onMutate: async ({ id, ack }) => {
      await queryClient.cancelQueries({ queryKey: ['alerts'] })
      const prev = queryClient.getQueryData<Alert[]>(['alerts']) ?? []
      queryClient.setQueryData<Alert[]>(
        ['alerts'],
        prev.map((a) => (a.id === id ? { ...a, acknowledged: ack } : a)),
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) queryClient.setQueryData(['alerts'], ctx.prev)
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  const handleAck = (id: string) => {
    setAckedLocal((prev) => (prev.includes(id) ? prev : [...prev, id]))
    ackMutation.mutate({ id, ack: true })
  }

  const merged = alerts.map((a) => ({
    ...a,
    acknowledged: a.acknowledged || ackedLocal.includes(a.id),
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
            onAck={handleAck}
          />
        ))}
      </CardContent>
    </Card>
  )
}

// --- Live camera feeds ----------------------------------------------------

function CCTVTimestamp() {
  const [time, setTime] = useState(() => new Date())

  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000)
    return () => clearInterval(id)
  }, [])

  return <span suppressHydrationWarning>{formatTime(time.toISOString())} IST</span>
}

// --- Single camera tile with live MJPEG feed --------------------------------

function CameraStreamTile({ camera }: { camera: { id: string; name: string; ipAddress?: string; zone?: string; status: string } }) {
  const tileRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLImageElement>(null)
  const [streamError, setStreamError] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const streamUrl = getCameraStreamUrl(camera.id)

  // Reset error state so we retry when the component re-mounts or camera changes
  useEffect(() => {
    setStreamError(false)
  }, [camera.id])

  useEffect(() => {
    function syncFullscreenState() {
      setIsFullscreen(document.fullscreenElement === tileRef.current)
    }

    document.addEventListener('fullscreenchange', syncFullscreenState)
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState)
  }, [])

  async function toggleFullscreen() {
    if (!tileRef.current) return

    if (document.fullscreenElement === tileRef.current) {
      await document.exitFullscreen()
      return
    }

    await tileRef.current.requestFullscreen()
  }

  return (
    <div
      ref={tileRef}
      className="group relative aspect-video overflow-hidden rounded-lg border border-border bg-black shadow-inner [&:fullscreen]:h-screen [&:fullscreen]:w-screen [&:fullscreen]:rounded-none [&:fullscreen]:border-0"
    >
      {/* Live MJPEG stream */}
      {!streamError ? (
        <img
          ref={imgRef}
          src={streamUrl}
          alt={`Live feed – ${camera.name}`}
          className="absolute inset-0 h-full w-full object-contain"
          onError={() => setStreamError(true)}
        />
      ) : (
        /* Fallback when stream is unreachable */
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-muted/10">
          <Video className="size-8 text-muted-foreground/40" />
          <p className="font-mono text-[11px] text-muted-foreground/60">Stream unavailable</p>
          <button
            className="rounded border border-border px-2 py-0.5 font-mono text-[10px] text-muted-foreground hover:bg-muted/30 transition-colors"
            onClick={() => setStreamError(false)}
          >
            Retry
          </button>
        </div>
      )}

      {/* Scanlines overlay — preserved for CCTV aesthetic */}
      <div className="absolute inset-0 pointer-events-none opacity-10 bg-[linear-gradient(rgba(255,255,255,0)_50%,rgba(0,0,0,0.35)_50%)] bg-[length:100%_3px]" />

      <Button
        type="button"
        size="icon-sm"
        variant="ghost"
        aria-label={isFullscreen ? 'Exit fullscreen camera feed' : 'Open fullscreen camera feed'}
        title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
        className="absolute right-2 top-1/2 z-10 -translate-y-1/2 border border-white/15 bg-black/55 text-white/80 shadow-lg backdrop-blur-sm hover:bg-black/80 hover:text-white focus-visible:border-white/40 focus-visible:ring-white/25"
        onClick={(event) => {
          event.stopPropagation()
          void toggleFullscreen()
        }}
      >
        {isFullscreen ? <Minimize2 /> : <Maximize2 />}
      </Button>

      {/* Top HUD */}
      <div className="absolute top-2 left-2 right-2 flex items-center justify-between font-mono text-[10px] sm:text-[11px] font-semibold text-white/90 drop-shadow-md">
        <div className="flex items-center gap-1.5">
          <div className="flex items-center gap-1.5 rounded-sm bg-black/60 px-2 py-0.5 border border-white/10">
            <div className="size-1.5 rounded-full bg-red-500 animate-pulse" />
            LIVE
          </div>
          <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10 truncate max-w-[120px]">
            {camera.name}
          </div>
        </div>
        <div
          className={cn(
            'rounded-sm px-2 py-0.5 border border-white/10 uppercase text-[9px] tracking-wide',
            camera.status === 'online'
              ? 'bg-emerald-900/60 text-emerald-300'
              : camera.status === 'degraded'
                ? 'bg-amber-900/60 text-amber-300'
                : 'bg-black/60 text-white/40',
          )}
        >
          {camera.status}
        </div>
      </div>

      {/* Bottom HUD */}
      <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between font-mono text-[10px] text-white/70 drop-shadow-md">
        <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10 truncate max-w-[60%]">
          {camera.ipAddress ? `IP: ${camera.ipAddress}` : camera.id} | {camera.zone || 'General'}
        </div>
        <div className="rounded-sm bg-black/60 px-2 py-0.5 border border-white/10">
          <CCTVTimestamp />
        </div>
      </div>
    </div>
  )
}

function LiveCameraFeeds() {
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => fetchCameras(),
  })

  const onlineCameras = cameras.filter(
    (c) => c.status === 'online' || c.status === 'degraded',
  )

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Video}
          title="Live Camera Feeds"
          count={onlineCameras.length}
          description="Real-time annotated video from the recognition pipeline"
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
              <CameraStreamTile key={c.id} camera={c} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// --- Presence & Passage Event Trail -----------------------------------------

const STATUS_FILTERS: Array<'all' | DetectionStatus> = [
  'all',
  'recognized',
  'flagged',
  'unknown',
]

const EPISODE_FILTERS = [
  { value: 'all', label: 'All Camera Visits' },
  { value: 'confirmed', label: '✓ Confirmed Only (>1s)' },
  { value: 'sustained', label: '⏱️ Sustained Dwell (>10s)' },
  { value: 'glance', label: '⚡ Instant Glances (<1s)' },
  { value: 'flagged', label: '🚨 Flagged / Alerts' },
] as const

function PresenceEventTrail() {
  const { mode, selectedBatchId } = useDashboardMode()
  const [viewMode, setViewMode] = useState<'episodes' | 'raw'>('episodes')
  const [gapThreshold, setGapThreshold] = useState<number>(45)
  const [episodeFilter, setEpisodeFilter] = useState<'all' | 'confirmed' | 'sustained' | 'glance' | 'flagged'>('all')
  const [rawStatus, setRawStatus] = useState<'all' | DetectionStatus>('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [expandedEpisodeId, setExpandedEpisodeId] = useState<string | null>(null)

  // Sorting state
  type SortField = 'in_time' | 'out_time' | 'dwell' | 'subject' | 'camera' | 'confidence' | 'detections'
  const [sortField, setSortField] = useState<SortField>('in_time')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc') // desc = newest / longest first

  const handleToggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDirection(field === 'subject' || field === 'camera' ? 'asc' : 'desc')
    }
    setPage(0)
  }

  // 1. Fetch Aggregated Camera Presence Episodes (In/Out & Dwell)
  const { data: episodes = [], isLoading: episodesLoading } = useQuery({
    queryKey: ['camera-episodes', mode, selectedBatchId, gapThreshold],
    queryFn: () => fetchCameraEpisodes(150, mode, selectedBatchId ?? undefined, undefined, undefined, gapThreshold),
    refetchInterval: mode === 'live' ? 3000 : false,
  })

  // 2. Fetch Granular Raw Detection Logs
  const { data: rawLogs = [], isLoading: logsLoading } = useQuery({
    queryKey: ['face-logs', mode, selectedBatchId],
    queryFn: () => fetchFaceLogs(150, 0, mode, selectedBatchId ?? undefined),
    refetchInterval: mode === 'live' ? 3000 : false,
  })

  // Confirmed vs Glance metrics
  const confirmedCount = useMemo(() => episodes.filter(e => e.dwellSeconds >= 1.0).length, [episodes])
  const glanceCount = useMemo(() => episodes.filter(e => e.dwellSeconds < 1.0).length, [episodes])

  // Filter Episodes
  const filteredEpisodes = useMemo(() => {
    return episodes.filter((ep) => {
      if (episodeFilter === 'flagged' && ep.status !== 'flagged') return false
      if (episodeFilter === 'confirmed' && ep.dwellSeconds < 1.0) return false
      if (episodeFilter === 'sustained' && ep.dwellSeconds < 10.0) return false
      if (episodeFilter === 'glance' && ep.dwellSeconds >= 1.0) return false
      if (query) {
        const q = query.toLowerCase()
        return (
          ep.id.toLowerCase().includes(q) ||
          ep.cameraName.toLowerCase().includes(q) ||
          ep.cameraId.toLowerCase().includes(q) ||
          ep.subjectName.toLowerCase().includes(q) ||
          (ep.zone?.toLowerCase().includes(q) ?? false) ||
          ep.direction.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [episodes, episodeFilter, query])

  // Filter Raw Logs
  const filteredRawLogs = useMemo(() => {
    return rawLogs.filter((l) => {
      if (rawStatus !== 'all' && l.status !== rawStatus) return false
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
  }, [rawLogs, rawStatus, query])

  // Sort Episodes
  const sortedEpisodes = useMemo(() => {
    return [...filteredEpisodes].sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'in_time':
          cmp = new Date(a.inTime).getTime() - new Date(b.inTime).getTime()
          break
        case 'out_time':
          cmp = new Date(a.outTime).getTime() - new Date(b.outTime).getTime()
          break
        case 'dwell':
          cmp = a.dwellSeconds - b.dwellSeconds
          break
        case 'subject':
          cmp = a.subjectName.localeCompare(b.subjectName)
          break
        case 'camera':
          cmp = a.cameraName.localeCompare(b.cameraName)
          break
        case 'confidence':
          cmp = a.peakConfidence - b.peakConfidence
          break
        case 'detections':
          cmp = a.detectionCount - b.detectionCount
          break
      }
      return sortDirection === 'asc' ? cmp : -cmp
    })
  }, [filteredEpisodes, sortField, sortDirection])

  // Sort Raw Logs
  const sortedRawLogs = useMemo(() => {
    return [...filteredRawLogs].sort((a, b) => {
      let cmp = 0
      switch (sortField) {
        case 'in_time':
        case 'out_time':
          cmp = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
          break
        case 'subject':
          cmp = (a.profileName || 'Unregistered').localeCompare(b.profileName || 'Unregistered')
          break
        case 'camera':
          cmp = a.cameraName.localeCompare(b.cameraName)
          break
        case 'confidence':
          cmp = (a.confidence || 0) - (b.confidence || 0)
          break
        default:
          cmp = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      }
      return sortDirection === 'asc' ? cmp : -cmp
    })
  }, [filteredRawLogs, sortField, sortDirection])

  const totalCount = viewMode === 'episodes' ? sortedEpisodes.length : sortedRawLogs.length
  const pageCount = Math.max(1, Math.ceil(totalCount / PAGE_SIZE))
  const current = Math.min(page, pageCount - 1)
  const episodeRows = sortedEpisodes.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)
  const rawRows = sortedRawLogs.slice(current * PAGE_SIZE, current * PAGE_SIZE + PAGE_SIZE)

  const handleInvestigateInForensic = (ep: CameraEpisode) => {
    // Dispatch tab switch to Forensic Search
    window.dispatchEvent(new CustomEvent('switch-dashboard-tab', { detail: 'forensic' }))
  }

  return (
    <Card className="gap-0 py-0 border-border/70 shadow-lg">
      <LineageDrawer eventId={selectedEventId} onClose={() => setSelectedEventId(null)} />
      
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Footprints}
          title={mode === 'archive' ? 'Archive Event Trail' : 'Camera Presence & Event Trail'}
          count={viewMode === 'episodes' ? episodes.length : rawLogs.length}
          description="Subject spatial tracking across cameras: discrete Entry (IN), Exit (OUT), and Dwell duration episodes"
          action={
            <div className="flex items-center gap-2">
              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value)
                    setPage(0)
                  }}
                  placeholder={viewMode === 'episodes' ? 'Search subject / camera / zone...' : 'Search raw event ID / subject...'}
                  className="h-8 w-56 pl-8 text-xs"
                />
              </div>

              {/* View Switcher: Episodes vs Raw */}
              <div className="flex rounded-md bg-muted p-0.5 border border-border/60">
                <button
                  type="button"
                  onClick={() => { setViewMode('episodes'); setPage(0); }}
                  className={cn(
                    "text-[11px] px-2.5 py-1 rounded transition-colors font-medium flex items-center gap-1.5",
                    viewMode === 'episodes'
                      ? "bg-background text-foreground shadow-sm font-semibold"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Footprints className="size-3 text-info" />
                  <span>In / Out Events</span>
                  <Badge variant="secondary" className="px-1 text-[9px] h-4 font-mono ml-0.5">
                    {episodes.length}
                  </Badge>
                </button>
                <button
                  type="button"
                  onClick={() => { setViewMode('raw'); setPage(0); }}
                  className={cn(
                    "text-[11px] px-2.5 py-1 rounded transition-colors font-medium flex items-center gap-1.5",
                    viewMode === 'raw'
                      ? "bg-background text-foreground shadow-sm font-semibold"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Layers className="size-3" />
                  <span>Raw Frames</span>
                  <Badge variant="outline" className="px-1 text-[9px] h-4 font-mono ml-0.5">
                    {rawLogs.length}
                  </Badge>
                </button>
              </div>
            </div>
          }
        />

        {/* Sub-Filters */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-border/40">
          <div className="flex flex-wrap items-center gap-1.5">
            {viewMode === 'episodes' ? (
              [
                { value: 'all' as const, label: 'All Visits', count: episodes.length },
                { value: 'confirmed' as const, label: '✓ Confirmed Only (>1s)', count: confirmedCount },
                { value: 'glance' as const, label: '⚡ Instant Glances (<1s)', count: glanceCount },
                { value: 'sustained' as const, label: '⏱️ Sustained Dwell (>10s)', count: episodes.filter(e => e.dwellSeconds >= 10.0).length },
                { value: 'flagged' as const, label: '🚨 Flagged', count: episodes.filter(e => e.status === 'flagged').length },
              ].map((f) => (
                <Button
                  key={f.value}
                  size="xs"
                  variant={episodeFilter === f.value ? 'secondary' : 'ghost'}
                  className={cn(
                    'text-[11px] h-7 gap-1.5',
                    episodeFilter === f.value && 'ring-1 ring-inset ring-border font-medium bg-muted'
                  )}
                  onClick={() => {
                    setEpisodeFilter(f.value)
                    setPage(0)
                  }}
                >
                  <span>{f.label}</span>
                  <span className={cn(
                    "text-[9px] font-mono px-1 rounded",
                    episodeFilter === f.value ? "bg-background text-foreground font-semibold" : "text-muted-foreground bg-muted/60"
                  )}>
                    {f.count}
                  </span>
                </Button>
              ))
            ) : (
              STATUS_FILTERS.map((s) => (
                <Button
                  key={s}
                  size="xs"
                  variant={rawStatus === s ? 'secondary' : 'ghost'}
                  className={cn('capitalize text-[11px] h-7', rawStatus === s && 'ring-1 ring-inset ring-border font-medium')}
                  onClick={() => {
                    setRawStatus(s)
                    setPage(0)
                  }}
                >
                  {s === 'all' ? 'All Raw Logs' : statusLabel[s]}
                </Button>
              ))
            )}
          </div>

          <div className="flex items-center gap-3">
            {/* Sort Dropdown */}
            <div className="flex items-center gap-1.5 text-[11px] bg-muted/40 px-2 py-0.5 rounded border border-border/50">
              <ArrowUpDown className="size-3 text-info shrink-0" />
              <span className="text-muted-foreground font-mono text-[10px]">Sort:</span>
              <select
                value={`${sortField}-${sortDirection}`}
                onChange={(e) => {
                  const [f, d] = e.target.value.split('-') as [SortField, 'asc' | 'desc']
                  setSortField(f)
                  setSortDirection(d)
                  setPage(0)
                }}
                className="bg-transparent text-[11px] font-mono text-foreground focus:outline-none cursor-pointer"
              >
                <option value="in_time-desc" className="bg-popover text-popover-foreground">🕒 Recent First (Newest Entry)</option>
                <option value="in_time-asc" className="bg-popover text-popover-foreground">⏳ Timeline Order (Oldest Entry)</option>
                <option value="dwell-desc" className="bg-popover text-popover-foreground">⏱️ Longest Dwell (High Presence)</option>
                <option value="dwell-asc" className="bg-popover text-popover-foreground">⚡ Shortest Dwell</option>
                <option value="confidence-desc" className="bg-popover text-popover-foreground">🎯 Peak Confidence (High → Low)</option>
                <option value="detections-desc" className="bg-popover text-popover-foreground">🎞️ Frame Count (Most Frames)</option>
                <option value="subject-asc" className="bg-popover text-popover-foreground">👤 Subject Name (A → Z)</option>
                <option value="camera-asc" className="bg-popover text-popover-foreground">📹 Camera Name (A → Z)</option>
              </select>
            </div>

            {viewMode === 'episodes' && (
              <div className="flex items-center gap-1.5 text-[11px] bg-muted/40 px-2 py-0.5 rounded border border-border/50">
                <SlidersHorizontal className="size-3 text-info shrink-0" />
                <span className="text-muted-foreground font-mono text-[10px]">Gap Window:</span>
                <div className="flex items-center gap-1">
                  {[
                    { label: '15s Strict', value: 15 },
                    { label: '45s Adaptive', value: 45 },
                    { label: '90s Room', value: 90 },
                  ].map((w) => (
                    <button
                      key={w.value}
                      type="button"
                      onClick={() => {
                        setGapThreshold(w.value)
                        setPage(0)
                      }}
                      className={cn(
                        "text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors",
                        gapThreshold === w.value
                          ? "bg-background text-foreground shadow-sm font-semibold border border-border/60 text-info"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {w.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="text-[11px] text-muted-foreground font-mono flex items-center gap-1.5">
              {viewMode === 'episodes' ? (
                <span className="flex items-center gap-1 text-info/90">
                  <Sparkles className="size-3 text-info" />
                  Aggregated {rawLogs.length} frames into {episodes.length} visits
                </span>
              ) : (
                <span>Showing individual frame-by-frame audit logs</span>
              )}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        {/* ================= VIEW MODE 1: In / Out Camera Presence Episodes ================= */}
        {viewMode === 'episodes' ? (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent bg-muted/20 text-[11px]">
                <TableHead
                  className="pl-4 cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('subject')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Subject</span>
                    {sortField === 'subject' ? (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    ) : (
                      <ArrowUpDown className="size-2.5 text-muted-foreground/40" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('camera')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Camera & Zone</span>
                    {sortField === 'camera' ? (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    ) : (
                      <ArrowUpDown className="size-2.5 text-muted-foreground/40" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('in_time')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>🟢 IN (Entry)</span>
                    {sortField === 'in_time' ? (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    ) : (
                      <ArrowUpDown className="size-2.5 text-muted-foreground/40" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('out_time')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>🔴 OUT (Exit)</span>
                    {sortField === 'out_time' ? (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    ) : (
                      <ArrowUpDown className="size-2.5 text-muted-foreground/40" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('dwell')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Dwell Duration</span>
                    {sortField === 'dwell' ? (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    ) : (
                      <ArrowUpDown className="size-2.5 text-muted-foreground/40" />
                    )}
                  </div>
                </TableHead>
                <TableHead>Movement Flow</TableHead>
                <TableHead>Transit Handoff</TableHead>
                <TableHead className="pr-4 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {episodeRows.map((ep) => {
                const isExpanded = expandedEpisodeId === ep.id
                return (
                  <Fragment key={ep.id}>
                    <TableRow key={`${ep.id}-main`} className={cn("transition-colors", ep.isActive && "bg-info/5")}>
                      {/* 1. Subject */}
                      <TableCell className="pl-4">
                        <div className="flex items-center gap-2.5">
                          <FaceTile
                            tone={ep.snapshotTone}
                            image={ep.inFaceImage || ep.outFaceImage}
                            size="md"
                            flagged={ep.status === 'flagged'}
                          />
                          <div className="flex flex-col min-w-0">
                            <div className="flex items-center gap-1.5">
                              <span className="text-sm font-semibold text-foreground truncate">
                                {ep.subjectName}
                              </span>
                              <RoleBadge role={ep.role as any} />
                            </div>
                            <span className="text-[10px] font-mono text-muted-foreground truncate">
                              {ep.subjectId ? ep.subjectId.slice(0, 16) : 'Unregistered'}
                            </span>
                          </div>
                        </div>
                      </TableCell>

                      {/* 2. Camera & Zone */}
                      <TableCell>
                        <div className="flex flex-col">
                          <span className="text-xs font-medium text-foreground">{ep.cameraName}</span>
                          <span className="text-[10px] font-mono text-muted-foreground">{ep.zone || ep.cameraId}</span>
                        </div>
                      </TableCell>

                      {/* 3. IN (Entry) */}
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {ep.inFaceImage ? (
                            <img
                              src={ep.inFaceImage.startsWith('data:') ? ep.inFaceImage : `data:image/jpeg;base64,${ep.inFaceImage}`}
                              alt="Entry crop"
                              className="size-7 rounded object-cover ring-1 ring-emerald-500/50 shrink-0"
                            />
                          ) : (
                            <div className="size-7 rounded bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center shrink-0">
                              <LogIn className="size-3.5 text-emerald-400" />
                            </div>
                          )}
                          <div className="flex flex-col">
                            <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-emerald-400">
                              <LogIn className="size-2.5" /> {formatTime(ep.inTime)}
                            </span>
                            <span className="text-[9px] text-muted-foreground">Entry Detected</span>
                          </div>
                        </div>
                      </TableCell>

                      {/* 4. OUT (Exit) */}
                      <TableCell>
                        {ep.isActive ? (
                          <div className="flex items-center gap-1.5">
                            <span className="relative flex size-2">
                              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-info opacity-75" />
                              <span className="relative inline-flex rounded-full size-2 bg-info" />
                            </span>
                            <span className="text-xs font-semibold text-info font-mono">Present Now</span>
                          </div>
                        ) : ep.dwellSeconds === 0 ? (
                          <div className="flex items-center gap-2">
                            <div className="size-7 rounded bg-muted/30 border border-border/40 flex items-center justify-center shrink-0">
                              <Clock className="size-3 text-muted-foreground/60" />
                            </div>
                            <div className="flex flex-col">
                              <span className="font-mono text-xs text-muted-foreground">
                                --:--:--
                              </span>
                              <span className="text-[9px] text-muted-foreground/80">Single sighting</span>
                            </div>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            {ep.outFaceImage ? (
                              <img
                                src={ep.outFaceImage.startsWith('data:') ? ep.outFaceImage : `data:image/jpeg;base64,${ep.outFaceImage}`}
                                alt="Exit crop"
                                className="size-7 rounded object-cover ring-1 ring-rose-500/50 shrink-0"
                              />
                            ) : (
                              <div className="size-7 rounded bg-rose-500/10 border border-rose-500/30 flex items-center justify-center shrink-0">
                                <LogOut className="size-3.5 text-rose-400" />
                              </div>
                            )}
                            <div className="flex flex-col">
                              <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-rose-400">
                                <LogOut className="size-2.5" /> {formatTime(ep.outTime)}
                              </span>
                              <span className="text-[9px] text-muted-foreground">Exit Detected</span>
                            </div>
                          </div>
                        )}
                      </TableCell>

                      {/* 5. Dwell Duration */}
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <div className="flex items-center gap-1.5">
                            {ep.dwellSeconds === 0 ? (
                              <Badge
                                variant="outline"
                                className="font-mono text-[10px] px-1.5 py-0 border-border/60 text-muted-foreground bg-muted/20 flex items-center gap-1"
                              >
                                <Sparkles className="size-2.5 text-amber-400" />
                                ⚡ Instant Glance (&lt;1s)
                              </Badge>
                            ) : (
                              <Badge
                                variant="outline"
                                className={cn(
                                  "font-mono text-[11px] px-1.5 py-0 flex items-center gap-1 font-semibold",
                                  ep.dwellSeconds > 60 ? "border-amber-500/40 text-amber-400 bg-amber-500/10" :
                                  ep.dwellSeconds >= 5 ? "border-info/40 text-info bg-info/10" :
                                  "border-emerald-500/40 text-emerald-400 bg-emerald-500/10"
                                )}
                              >
                                <Clock className="size-2.5" />
                                {ep.dwellSeconds >= 60
                                  ? `${(ep.dwellSeconds / 60).toFixed(1)}m dwell`
                                  : `${ep.dwellSeconds.toFixed(1)}s dwell`}
                              </Badge>
                            )}
                          </div>
                          <span className="text-[10px] text-muted-foreground font-mono">
                            {ep.detectionCount} {ep.detectionCount === 1 ? 'frame' : 'frames'} · {ep.peakConfidence.toFixed(0)}% peak
                          </span>
                        </div>
                      </TableCell>

                      {/* 6. Movement Flow */}
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          {ep.dwellSeconds === 0 ? (
                            <span className="text-[11px] text-muted-foreground font-medium flex items-center gap-1 bg-muted/20 px-2 py-0.5 rounded border border-border/30">
                              <Sparkles className="size-2.5 text-amber-400/80" /> Fleeting Sighting
                            </span>
                          ) : (
                            <span className="text-xs text-foreground font-medium flex items-center gap-1 bg-muted/40 px-2 py-0.5 rounded border border-border/40">
                              <Compass className="size-3 text-info" /> {ep.direction}
                            </span>
                          )}
                        </div>
                      </TableCell>

                      {/* 7. Transit Handoff */}
                      <TableCell>
                        {ep.nextCameraName ? (
                          <div className="flex items-center gap-1 text-[11px] font-mono text-info bg-info/10 border border-info/30 px-2 py-0.5 rounded">
                            <ArrowRight className="size-3 text-info shrink-0" />
                            <span className="truncate max-w-[110px] font-medium">{ep.nextCameraName}</span>
                            {ep.transitSeconds != null && (
                              <span className="text-[9px] text-muted-foreground">({ep.transitSeconds}s)</span>
                            )}
                          </div>
                        ) : (
                          <span className="text-[11px] text-muted-foreground/60 font-mono">End of route</span>
                        )}
                      </TableCell>

                      {/* 8. Actions */}
                      <TableCell className="pr-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            size="xs"
                            variant="outline"
                            className="h-7 gap-1 font-mono text-[11px] hover:border-info hover:text-info"
                            title="Trace subject trajectory across all cameras"
                            onClick={() => handleInvestigateInForensic(ep)}
                          >
                            <Search className="size-3 text-info" />
                            <span>Trajectory</span>
                          </Button>
                          <Button
                            size="xs"
                            variant="ghost"
                            className="h-7 px-2 font-mono text-[11px]"
                            title="Toggle individual frame detections"
                            onClick={() => setExpandedEpisodeId(isExpanded ? null : ep.id)}
                          >
                            {isExpanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>

                    {/* Inline Expandable Frame Chips */}
                    {isExpanded && (
                      <TableRow className="bg-muted/30 border-y border-border/80">
                        <TableCell colSpan={8} className="p-3 pl-8">
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                                <Layers className="size-3 text-info" /> Frame Detections Inside This Passage Episode ({ep.detectionIds.length})
                              </span>
                              <Button
                                size="xs"
                                variant="outline"
                                className="h-6 gap-1 text-[10px]"
                                onClick={() => setSelectedEventId(ep.detectionIds[0])}
                              >
                                <Workflow className="size-2.5 text-primary" /> View Lineage Audit
                              </Button>
                            </div>
                            <div className="flex flex-wrap gap-2 pt-1">
                              {ep.detectionIds.map((dId, idx) => (
                                <div
                                  key={dId}
                                  className="flex items-center gap-1.5 bg-card border border-border px-2 py-1 rounded text-[10px] font-mono text-muted-foreground hover:border-info/50 cursor-pointer"
                                  onClick={() => setSelectedEventId(dId)}
                                >
                                  <span className="size-1.5 rounded-full bg-info" />
                                  <span>Frame #{idx + 1}</span>
                                  <span className="text-foreground/80">({dId.slice(0, 8)})</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
              {episodeRows.length === 0 && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={8} className="py-12 text-center text-muted-foreground">
                    No camera presence episodes match the current filter.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        ) : (
          /* ================= VIEW MODE 2: Granular Raw Detection Log ================= */
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent bg-muted/20 text-[11px]">
                <TableHead className="pl-4">Snapshot</TableHead>
                <TableHead>Event ID</TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('subject')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Subject</span>
                    {sortField === 'subject' && (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('camera')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Camera</span>
                    {sortField === 'camera' && (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('in_time')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Time (IST)</span>
                    {sortField === 'in_time' && (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    )}
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer select-none hover:text-foreground transition-colors"
                  onClick={() => handleToggleSort('confidence')}
                >
                  <div className="flex items-center gap-1 font-semibold">
                    <span>Confidence</span>
                    {sortField === 'confidence' && (
                      sortDirection === 'asc' ? <ChevronUp className="size-3 text-info" /> : <ChevronDown className="size-3 text-info" />
                    )}
                  </div>
                </TableHead>
                <TableHead>Liveness</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="pr-4 text-right">Lineage</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rawRows.map((l) => (
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
                    <div className="flex items-center gap-2.5">
                      <FaceTile tone={l.snapshotTone} image={l.faceImage} size="sm" />
                      <span className="text-sm">
                        {l.profileName ?? (
                          <span className="text-muted-foreground">Unidentified</span>
                        )}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    <span className="font-mono text-xs">{l.cameraId}</span>{' '}
                    {l.cameraName}
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground" title={formatDateTime(l.timestamp)}>
                    {formatTime(l.timestamp)} <span className="text-[10px] text-muted-foreground/60 font-sans">IST</span>
                  </TableCell>
                  <TableCell>
                    <ConfidenceMeter value={l.confidence} />
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                    {l.livenessScore}
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={l.status} />
                  </TableCell>
                  <TableCell className="pr-4 text-right">
                    <Button
                      size="xs"
                      variant="outline"
                      className="h-7 gap-1 font-mono text-[11px]"
                      onClick={() => setSelectedEventId(l.id)}
                    >
                      <Workflow className="size-3 text-primary" />
                      <span>Lineage</span>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {rawRows.length === 0 && (
                <TableRow className="hover:bg-transparent">
                  <TableCell colSpan={9} className="py-10 text-center text-muted-foreground">
                    No raw events match the current filters.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        )}
      </CardContent>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-border px-4 py-2.5 bg-card/40">
        <p className="font-mono text-xs text-muted-foreground">
          Page {current + 1} / {pageCount} · {totalCount} {viewMode === 'episodes' ? 'presence episodes' : 'raw detections'}
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
  const { mode } = useDashboardMode()
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-4">
        {mode === 'live' && <LiveCameraFeeds />}
        <PresenceEventTrail />
      </div>
      <AlertSidebar />
    </div>
  )
}
