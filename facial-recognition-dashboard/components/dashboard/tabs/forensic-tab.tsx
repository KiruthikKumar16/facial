'use client'

import { useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  fetchCameras,
  fetchFootfall,
  fetchMovementNetwork,
  fetchTrajectory,
  runForensicSearch,
  type ForensicSearchPayload,
} from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  ConfidenceMeter,
  FaceTile,
  RoleBadge,
  SectionHeading,
} from '@/components/dashboard/shared'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ForensicMatch, Gender } from '@/lib/types'
import {
  ChartColumnBig,
  Glasses,
  ImageUp,
  MapPin,
  Route,
  ArrowRight,
  ScanSearch,
  UploadCloud,
  VenetianMask,
  X,
} from 'lucide-react'

function FootfallSummary() {
  const { data = [] } = useQuery({
    queryKey: ['forensic-footfall'],
    queryFn: () => fetchFootfall(1),
  })
  const peak = Math.max(...data.map((bucket) => bucket.detections), 1)

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={ChartColumnBig}
          title="Recent Footfall"
          description="Hourly detections across all camera nodes"
        />
      </CardHeader>
      <CardContent className="p-4">
        <div className="flex h-32 items-end gap-1">
          {data.map((bucket) => (
            <div key={bucket.hour} className="group flex min-w-0 flex-1 flex-col items-center gap-1">
              <div
                className="w-full rounded-t-sm bg-info/70 transition-colors group-hover:bg-info"
                style={{ height: `${Math.max((bucket.detections / peak) * 100, bucket.detections ? 6 : 1)}%` }}
                title={`${bucket.hour}: ${bucket.detections} detections`}
              />
              <span className="truncate text-[9px] text-muted-foreground">{bucket.hour}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
          <span>Recognized: <strong className="text-foreground">{data.reduce((sum, bucket) => sum + bucket.recognized, 0)}</strong></span>
          <span>Unknown: <strong className="text-foreground">{data.reduce((sum, bucket) => sum + bucket.unknown, 0)}</strong></span>
        </div>
      </CardContent>
    </Card>
  )
}

function Dropzone({
  file,
  onFile,
  onClear,
}: {
  file: File | null
  onFile: (f: File) => void
  onClear: () => void
}) {
  const [dragging, setDragging] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleFile(f: File) {
    onFile(f)
    const url = URL.createObjectURL(f)
    setPreview(url)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const f = e.dataTransfer.files?.[0]
        if (f) handleFile(f)
      }}
      className={cn(
        'relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border bg-card/40 p-8 text-center transition-colors',
        dragging && 'border-info bg-info/5',
      )}
    >
      {preview ? (
        <div className="flex flex-col items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={preview || '/placeholder.svg'}
            alt="Uploaded probe face for 1:N search"
            className="size-28 rounded-md object-cover ring-1 ring-border"
          />
          <div className="flex items-center gap-2">
            <span className="max-w-40 truncate font-mono text-xs text-muted-foreground">
              {file?.name}
            </span>
            <Button
              size="icon-xs"
              variant="ghost"
              onClick={() => {
                onClear()
                setPreview(null)
              }}
            >
              <X />
            </Button>
          </div>
        </div>
      ) : (
        <>
          <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <UploadCloud className="size-6" />
          </span>
          <div>
            <p className="text-sm font-medium">Drop a probe image to run 1:N match</p>
            <p className="mt-1 text-xs text-muted-foreground">
              JPG / PNG · face is embedded & searched against the vector index
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={() => inputRef.current?.click()}>
            <ImageUp /> Browse files
          </Button>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) handleFile(f)
        }}
      />
    </div>
  )
}

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors',
        active
          ? 'border-info/40 bg-info/15 text-info'
          : 'border-border bg-card/50 text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

function MatchRow({ match }: { match: ForensicMatch }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card/50 p-2.5">
      <FaceTile tone={match.avatarTone} size="md" flagged={match.role === 'blacklist'} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium">{match.profileName}</p>
          {match.role ? <RoleBadge role={match.role} /> : null}
        </div>
        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
          Last seen {formatTime(match.lastSeen)} · {match.cameraName}
        </p>
      </div>
      <div className="text-right">
        <p className="font-mono text-sm font-semibold tabular-nums text-info">
          {(match.cosineSimilarity * 100).toFixed(1)}%
        </p>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
          cosine
        </p>
      </div>
    </div>
  )
}

function TrajectoryTimeline() {
  const { data: trajectory } = useQuery({
    queryKey: ['trajectory'],
    queryFn: () => fetchTrajectory(),
  })
  if (!trajectory) return null

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Route}
          title="Subject Movement Trajectory"
          description={`Reconstructed path · ${trajectory.profileName}`}
        />
      </CardHeader>
      <CardContent className="p-4">
        <ol className="relative flex flex-col gap-0">
          {trajectory.path.map((node, i) => {
            const isLast = i === trajectory.path.length - 1
            return (
              <li key={`${node.cameraId}-${i}`} className="relative flex gap-4 pb-6 last:pb-0">
                {!isLast && (
                  <span className="absolute left-[27px] top-14 h-[calc(100%-3.5rem)] w-px bg-gradient-to-b from-info/60 to-border" />
                )}
                <FaceTile tone={node.snapshotTone} size="lg" />
                <div className="flex-1 rounded-lg border border-border bg-card/50 p-3">
                  <div className="flex items-center justify-between">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      <MapPin className="size-3.5 text-info" />
                      {node.cameraId} · {node.cameraName}
                    </p>
                    <span className="font-mono text-xs text-muted-foreground">
                      {formatTime(node.timestamp)}
                    </span>
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Zone: {node.zone}
                  </p>
                  <div className="mt-2">
                    <ConfidenceMeter value={node.confidence} />
                  </div>
                </div>
              </li>
            )
          })}
        </ol>
      </CardContent>
    </Card>
  )
}

function MovementNetwork() {
  const { data } = useQuery({
    queryKey: ['movement-network'],
    queryFn: () => fetchMovementNetwork(24),
  })

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Route}
          title="Camera Movement Network"
          description="Identified-person handoffs in the last 24 hours"
        />
      </CardHeader>
      <CardContent className="p-4">
        {data?.edges.length ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {data.edges.map((edge) => (
              <div key={`${edge.fromCameraId}-${edge.toCameraId}`} className="flex items-center gap-2 rounded-lg border border-border bg-card/50 p-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{edge.fromCameraName}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{edge.fromCameraId}</p>
                </div>
                <ArrowRight className="size-4 shrink-0 text-info" />
                <div className="min-w-0 flex-1 text-right">
                  <p className="truncate text-sm font-medium">{edge.toCameraName}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">{edge.toCameraId}</p>
                </div>
                <span className="rounded bg-info/10 px-1.5 py-1 font-mono text-[10px] text-info">{edge.count}x</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No cross-camera handoffs recorded yet.</p>
        )}
      </CardContent>
    </Card>
  )
}

export function ForensicTab() {
  const { data: cameras = [] } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => fetchCameras(),
  })
  const [file, setFile] = useState<File | null>(null)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [selectedCameras, setSelectedCameras] = useState<string[]>([])
  const [gender, setGender] = useState<Gender | 'all'>('all')
  const [ageRange, setAgeRange] = useState<number[]>([18, 65])
  const [mask, setMask] = useState(false)
  const [glasses, setGlasses] = useState(false)

  const search = useMutation<ForensicMatch[], Error, ForensicSearchPayload>({
    mutationFn: runForensicSearch,
  })

  function toggleCamera(id: string) {
    setSelectedCameras((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id],
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[420px_1fr]">
      {/* Query builder */}
      <div className="flex flex-col gap-4">
        <MovementNetwork />
        <FootfallSummary />
        <Card className="gap-0 py-0">
          <CardHeader className="border-b border-border py-3">
            <SectionHeading
              icon={ScanSearch}
              title="Reverse Image Search"
              description="1:N face matching against the biometric index"
            />
          </CardHeader>
          <CardContent className="flex flex-col gap-4 p-4">
            <Dropzone
              file={file}
              onFile={setFile}
              onClear={() => setFile(null)}
            />

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">From</Label>
                <Input
                  type="datetime-local"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs text-muted-foreground">To</Label>
                <Input
                  type="datetime-local"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">
                Camera Nodes ({selectedCameras.length || 'all'})
              </Label>
              <div className="flex flex-wrap gap-1.5">
                {cameras.map((c) => (
                  <Chip
                    key={c.id}
                    active={selectedCameras.includes(c.id)}
                    onClick={() => toggleCamera(c.id)}
                  >
                    {c.id}
                  </Chip>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Gender</Label>
              <div className="flex flex-wrap gap-1.5">
                {(['all', 'male', 'female', 'unknown'] as const).map((g) => (
                  <Chip key={g} active={gender === g} onClick={() => setGender(g)}>
                    <span className="capitalize">{g}</span>
                  </Chip>
                ))}
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Age Range</Label>
                <span className="font-mono text-xs text-foreground">
                  {ageRange[0]} – {ageRange[1]}
                </span>
              </div>
              <Slider
                value={ageRange}
                onValueChange={(v) => setAgeRange(Array.isArray(v) ? v : [v, v])}
                min={0}
                max={90}
                step={1}
              />
            </div>

            <div className="space-y-2">
              <Label className="text-xs text-muted-foreground">Accessories</Label>
              <div className="flex flex-wrap gap-1.5">
                <Chip active={mask} onClick={() => setMask((v) => !v)}>
                  <VenetianMask className="size-3.5" /> Mask
                </Chip>
                <Chip active={glasses} onClick={() => setGlasses((v) => !v)}>
                  <Glasses className="size-3.5" /> Glasses
                </Chip>
              </div>
            </div>

            <Button
              onClick={() => {
                if (!file) return
                search.mutate({
                  imageFile: file,
                  from: dateFrom,
                  to: dateTo,
                  cameraIds: selectedCameras,
                  gender,
                  ageRange,
                  wearingMask: mask,
                  wearingGlasses: glasses,
                })
              }}
              disabled={!file || search.isPending}
              className="w-full"
            >
              <ScanSearch />
              {search.isPending ? 'Searching vector index…' : 'Run 1:N Search'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Results + trajectory */}
      <div className="flex flex-col gap-4">
        <Card className="gap-0 py-0">
          <CardHeader className="border-b border-border py-3">
            <SectionHeading
              icon={ScanSearch}
              title="Candidate Matches"
              count={search.data?.length}
              description="Ranked by cosine similarity of face embeddings"
            />
          </CardHeader>
          <CardContent className="p-3">
            {search.isPending ? (
              <div className="space-y-2.5">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-16 animate-pulse rounded-lg border border-border bg-muted/40"
                  />
                ))}
              </div>
            ) : search.isError ? (
              <div className="flex flex-col items-center gap-2 py-12 text-center">
                <ScanSearch className="size-8 text-destructive" />
                <p className="text-sm text-muted-foreground">
                  {search.error.message || 'Forensic search failed.'}
                </p>
              </div>
            ) : search.data ? (
              <div className="space-y-2.5">
                {search.data.length > 0 ? (
                  search.data.map((m, i) => (
                    <MatchRow key={`${m.profileId ?? 'unk'}-${i}`} match={m} />
                  ))
                ) : (
                  <div className="flex flex-col items-center gap-2 py-12 text-center">
                    <ScanSearch className="size-8 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      No candidate matches met the current search filters.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center gap-2 py-12 text-center">
                <ScanSearch className="size-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  Upload a probe image and run a search to see ranked candidates.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <TrajectoryTimeline />
      </div>
    </div>
  )
}
