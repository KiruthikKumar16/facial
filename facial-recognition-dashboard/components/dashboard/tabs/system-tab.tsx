'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { fetchCameras, fetchThresholds, saveThresholds } from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { SectionHeading } from '@/components/dashboard/shared'
import { cn } from '@/lib/utils'
import { formatTime } from '@/lib/format'
import type { Camera, CameraStatus, ModelThresholds } from '@/lib/types'
import {
  Cctv,
  Cpu,
  Gauge,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Wifi,
  WifiOff,
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

function CameraCard({ camera }: { camera: Camera }) {
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
          <span className={cn('flex items-center gap-1.5 text-xs font-medium', meta.text)}>
            <span className={cn('size-2 rounded-full', meta.dot)} />
            {meta.label}
          </span>
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

function CameraGrid() {
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: fetchCameras,
  })
  const online = cameras.filter((c) => c.status === 'online').length
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Cctv}
          title="Camera Node Health"
          description={`${online}/${cameras.length} nodes streaming · RTSP ingest pipeline`}
          action={
            <Badge className="rounded-md bg-muted font-mono text-muted-foreground">
              GPU cluster: 2× A10G
            </Badge>
          }
        />
      </CardHeader>
      <CardContent className="p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {cameras.map((c) => (
            <CameraCard key={c.id} camera={c} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function ThresholdSlider({
  label,
  description,
  value,
  min,
  max,
  suffix,
  onChange,
}: {
  label: string
  description: string
  value: number
  min: number
  max: number
  suffix?: string
  onChange: (v: number) => void
}) {
  return (
    <div className="space-y-2.5 rounded-lg border border-border bg-card/50 p-3.5">
      <div className="flex items-center justify-between">
        <Label className="text-sm">{label}</Label>
        <span className="font-mono text-sm font-semibold tabular-nums text-info">
          {value}
          {suffix}
        </span>
      </div>
      <Slider
        value={[value]}
        min={min}
        max={max}
        step={1}
        onValueChange={(v) => onChange(Array.isArray(v) ? v[0] : v)}
      />
      <p className="text-xs text-muted-foreground">{description}</p>
    </div>
  )
}

function ThresholdPanel() {
  const { data } = useQuery({ queryKey: ['thresholds'], queryFn: fetchThresholds })
  const save = useMutation({ mutationFn: saveThresholds })
  const [draft, setDraft] = useState<ModelThresholds | null>(null)

  useEffect(() => {
    if (data && !draft) setDraft(data)
  }, [data, draft])

  if (!draft) {
    return (
      <Card className="h-48 animate-pulse py-0">
        <CardContent className="p-4" />
      </Card>
    )
  }

  const dirty = JSON.stringify(draft) !== JSON.stringify(data)

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={SlidersHorizontal}
          title="Model Thresholds"
          description="Live tuning of global recognition parameters"
        />
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4">
        <ThresholdSlider
          label="Recognition Confidence"
          description="Minimum cosine confidence to accept an identity match."
          value={draft.recognitionConfidence}
          min={50}
          max={99}
          suffix="%"
          onChange={(v) => setDraft({ ...draft, recognitionConfidence: v })}
        />
        <ThresholdSlider
          label="Liveness Score"
          description="Minimum anti-spoofing score before a face is trusted."
          value={draft.livenessScore}
          min={0}
          max={100}
          onChange={(v) => setDraft({ ...draft, livenessScore: v })}
        />
        <ThresholdSlider
          label="Unknown Face Retention"
          description="Days to retain unmatched captures before purge."
          value={draft.unknownFaceRetentionDays}
          min={1}
          max={90}
          suffix="d"
          onChange={(v) => setDraft({ ...draft, unknownFaceRetentionDays: v })}
        />

        <button
          type="button"
          onClick={() =>
            setDraft({ ...draft, autoAlertOnBlacklist: !draft.autoAlertOnBlacklist })
          }
          className="flex items-center justify-between rounded-lg border border-border bg-card/50 p-3.5 text-left"
        >
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="size-4 text-info" />
            <div>
              <p className="text-sm">Auto-alert on blacklist hit</p>
              <p className="text-xs text-muted-foreground">
                Raise a critical alert instantly on any BOLO match.
              </p>
            </div>
          </div>
          <span
            className={cn(
              'relative h-5 w-9 rounded-full transition-colors',
              draft.autoAlertOnBlacklist ? 'bg-info' : 'bg-muted',
            )}
          >
            <span
              className={cn(
                'absolute top-0.5 size-4 rounded-full bg-background transition-transform',
                draft.autoAlertOnBlacklist ? 'left-0.5 translate-x-4' : 'left-0.5',
              )}
            />
          </span>
        </button>

        <div className="flex items-center justify-between border-t border-border pt-3">
          <p className="text-xs text-muted-foreground">
            {save.isSuccess && !dirty
              ? 'Thresholds pushed to all nodes.'
              : dirty
                ? 'Unsaved changes'
                : 'Synced with edge nodes'}
          </p>
          <Button
            size="sm"
            disabled={!dirty || save.isPending}
            onClick={() => save.mutate(draft)}
          >
            <Gauge /> {save.isPending ? 'Applying…' : 'Apply Thresholds'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function ServerVitals() {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading icon={Cpu} title="Inference Server" description="Aggregate load" />
      </CardHeader>
      <CardContent className="flex flex-col gap-3 p-4">
        <LoadBar label="GPU cluster" value={68} tone="bg-info" />
        <LoadBar label="CPU" value={44} tone="bg-info" />
        <LoadBar label="VRAM" value={73} tone="bg-warning" />
        <LoadBar label="Vector index memory" value={51} tone="bg-info" />
        <div className="grid grid-cols-2 gap-2 border-t border-border pt-3 text-center">
          <div>
            <p className="font-mono text-lg font-semibold tabular-nums">58ms</p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Avg latency
            </p>
          </div>
          <div>
            <p className="font-mono text-lg font-semibold tabular-nums">1.2M</p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Indexed vectors
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function SystemTab() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_380px]">
      <CameraGrid />
      <div className="flex flex-col gap-4">
        <ThresholdPanel />
        <ServerVitals />
      </div>
    </div>
  )
}
