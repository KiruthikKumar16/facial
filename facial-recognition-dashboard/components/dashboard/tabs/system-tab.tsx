import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchCameras, fetchThresholds, saveThresholds, fetchNodeHealth } from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SectionHeading } from '@/components/dashboard/shared'
import { CameraConfigDialog } from '@/components/dashboard/camera-config-dialog'
import { cn } from '@/lib/utils'
import { formatTime } from '@/lib/format'
import type { Camera, CameraStatus, ModelThresholds, NodeHealthReport } from '@/lib/types'
import {
  Cctv,
  Cpu,
  Gauge,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Sliders,
  Wifi,
  WifiOff,
  Activity,
  HardDrive,
  Layers,
  Zap,
} from 'lucide-react'

const statusMeta: Record<
  CameraStatus,
  { label: string; dot: string; text: string }
> = {
  online: { label: 'Online', dot: 'bg-success', text: 'text-success' },
  degraded: { label: 'Degraded', dot: 'bg-warning', text: 'text-warning' },
  offline: { label: 'Offline', dot: 'bg-destructive', text: 'text-destructive' },
}

function LoadBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums">{value}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full', tone)} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function CameraCard({
  camera,
  onConfigure,
}: {
  camera: Camera
  onConfigure: (camera: Camera) => void
}) {
  const meta = statusMeta[camera.status]
  const offline = camera.status === 'offline'
  const latencyTone =
    camera.frameLatencyMs > 100
      ? 'bg-destructive'
      : camera.frameLatencyMs > 60
        ? 'bg-warning'
        : 'bg-success'
  return (
    <Card
      className={cn(
        'gap-0 py-0',
        offline && 'opacity-70 ring-1 ring-inset ring-destructive/25',
      )}
    >
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
              {offline ? <WifiOff className="size-4.5" /> : <Cctv className="size-4.5" />}
            </span>
            <div>
              <p className="text-sm font-semibold">{camera.name}</p>
              <p className="font-mono text-[11px] text-muted-foreground">
                {camera.id} · {camera.zone}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className={cn('flex items-center gap-1.5 text-xs font-medium', meta.text)}>
              <span className={cn('size-2 rounded-full', meta.dot)} />
              {meta.label}
            </span>
            <Button
              size="xs"
              variant="outline"
              className="h-7 gap-1 px-2 font-mono text-[11px]"
              onClick={() => onConfigure(camera)}
            >
              <Sliders className="size-3 text-primary" />
              <span>Config</span>
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 rounded-md bg-muted/40 p-2.5 text-center">
          <div>
            <p className="font-mono text-sm font-semibold tabular-nums">
              {offline ? '—' : `${camera.pingMs}ms`}
            </p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Ping
            </p>
          </div>
          <div>
            <p className="font-mono text-sm font-semibold tabular-nums">
              {offline ? '—' : `${camera.frameLatencyMs}ms`}
            </p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Latency
            </p>
          </div>
          <div>
            <p className="font-mono text-sm font-semibold tabular-nums">
              {offline ? '—' : camera.fps}
            </p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              FPS
            </p>
          </div>
        </div>

        {!offline && (
          <>
            <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
              <div className={cn('h-full', latencyTone)} style={{ width: `${Math.min(100, camera.frameLatencyMs)}%` }} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <LoadBar
                label="GPU"
                value={camera.gpuLoad}
                tone={camera.gpuLoad > 85 ? 'bg-destructive' : 'bg-info'}
              />
              <LoadBar
                label="CPU"
                value={camera.cpuLoad}
                tone={camera.cpuLoad > 85 ? 'bg-destructive' : 'bg-info'}
              />
            </div>
          </>
        )}

        <div className="flex items-center justify-between border-t border-border pt-2.5 font-mono text-[11px] text-muted-foreground">
          <span>{camera.ipAddress}</span>
          <span>hb {formatTime(camera.lastHeartbeat)}</span>
        </div>
      </CardContent>
    </Card>
  )
}

function CameraGrid({ onConfigure }: { onConfigure: (camera: Camera) => void }) {
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => fetchCameras(),
  })
  const online = cameras.filter((c) => c.status === 'online').length
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <h2 className="text-lg font-semibold mt-2" data-testid="camera-node-health-heading">Camera Node Health</h2>
        <SectionHeading
          icon={Cctv}
          title="Camera Node Health"
          description={`${online}/${cameras.length} nodes streaming · Per-camera adaptive threshold profiles`}
          action={
            <Badge className="rounded-md bg-muted font-mono text-muted-foreground">
              Auto-sync: Active
            </Badge>
          }
        />
      </CardHeader>
      <CardContent className="p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {cameras.map((c) => (
            <CameraCard key={c.id} camera={c} onConfigure={onConfigure} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function NodeHealthPanel() {
  const { data: nodes = [], isLoading, isError } = useQuery({
    queryKey: ['node-health'],
    queryFn: () => fetchNodeHealth(),
    refetchInterval: 5000,
  })

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <h2 className="text-lg font-semibold mt-2" data-testid="edge-runtime-controller-heading">Edge Runtime Controller</h2>
        <SectionHeading
          icon={Activity}
          title="Edge Runtime Controller"
          description="Live health telemetry and adaptive throttling status across edge nodes"
        />
      </CardHeader>
      <CardContent className="p-4 space-y-3">
        {isLoading && (
          <div className="py-6 text-center text-xs text-muted-foreground animate-pulse">
            Connecting to runtime controller telemetry...
          </div>
        )}

        {isError && (
          <div className="rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning text-center">
            Runtime controller telemetry currently offline or in local fallback mode.
          </div>
        )}

        {nodes.length === 0 && !isLoading && !isError && (
          <div className="rounded-lg border border-border bg-muted/20 p-4 text-center text-xs text-muted-foreground">
            No external edge nodes reporting. Central node operating in NOMINAL mode.
          </div>
        )}

        {nodes.map((node) => {
          const isThrottled = node.runtimeMode === 'THROTTLED_COMPUTE'
          const isDegraded = node.runtimeMode === 'DEGRADED_NETWORK'
          const isEmergency = node.runtimeMode === 'EMERGENCY_DISK_PRESSURE'

          const modeBadgeClass = isEmergency
            ? 'bg-destructive/15 text-destructive border-destructive/30'
            : isThrottled || isDegraded
              ? 'bg-warning/15 text-warning border-warning/30'
              : 'bg-success/15 text-success border-success/30'

          return (
            <div key={node.nodeId} className="rounded-lg border border-border bg-card/60 p-3.5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="size-2 rounded-full bg-success animate-pulse" />
                  <span className="font-semibold text-sm">{node.nodeId}</span>
                  {node.hostname && (
                    <span className="font-mono text-xs text-muted-foreground">({node.hostname})</span>
                  )}
                </div>
                <Badge variant="outline" className={cn('font-mono text-[10px]', modeBadgeClass)}>
                  {node.runtimeMode}
                </Badge>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                <div className="rounded bg-muted/40 p-2">
                  <span className="text-muted-foreground block text-[10px]">CPU / Memory</span>
                  <span className="font-bold text-foreground">{node.cpuPercent.toFixed(1)}% / {node.memoryPercent.toFixed(1)}%</span>
                </div>
                <div className="rounded bg-muted/40 p-2">
                  <span className="text-muted-foreground block text-[10px]">FPS (Cam / Infer)</span>
                  <span className="font-bold text-foreground">{node.cameraFps.toFixed(1)} / {node.inferenceFps.toFixed(1)}</span>
                </div>
                <div className="rounded bg-muted/40 p-2">
                  <span className="text-muted-foreground block text-[10px]">Sync Queue / Lag</span>
                  <span className="font-bold text-foreground">{node.syncQueueLength} evts ({node.networkLatencyMs.toFixed(0)}ms)</span>
                </div>
                <div className="rounded bg-muted/40 p-2">
                  <span className="text-muted-foreground block text-[10px]">Sampling / Batch</span>
                  <span className="font-bold text-foreground">{node.frameSamplingRate}x / {node.syncBatchSize}</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] font-mono text-muted-foreground pt-1 border-t border-border/50">
                <span className="flex items-center gap-1">
                  <HardDrive className="size-3" /> Disk Free: {node.diskFreeMb} MB
                </span>
                <span>Reported {formatTime(node.reportedAt)}</span>
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

export function SystemTab() {
  const [configuredCamera, setConfiguredCamera] = useState<Camera | null>(null)

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
      <CameraConfigDialog
          camera={configuredCamera}
          onClose={() => setConfiguredCamera(null)}
        />

        <div className="flex flex-col gap-4">
          <CameraGrid onConfigure={(cam) => setConfiguredCamera(cam)} />
          <NodeHealthPanel />
        </div>
    </div>
  )
}
