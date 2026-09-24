'use client'

import { useRef, useState, useMemo, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  fetchCameras,
  fetchMovementNetwork,
  fetchTrajectory,
  runForensicSearch,
  fetchProfiles,
  fetchUnregisteredSubjects,
  type ForensicSearchPayload,
} from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FaceTile } from '@/components/dashboard/shared'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ForensicMatch, Gender } from '@/lib/types'
import {
  ImageUp, Route, ArrowRight, ScanSearch, UploadCloud, X, History, Activity, MonitorPlay, RotateCcw, Check, ChevronDown, Search
} from 'lucide-react'

// --- Normalization ---
function formatPercentage(val: number): string {
  if (val > 1) return val.toFixed(1) + '%'
  return (val * 100).toFixed(1) + '%'
}

function formatDuration(ms: number): string {
  const totalSecs = Math.floor(ms / 1000)
  const hours = Math.floor(totalSecs / 3600)
  const mins = Math.floor((totalSecs % 3600) / 60)
  const secs = totalSecs % 60
  
  if (hours > 0) return `${hours}h ${mins}m ${secs}s`
  if (mins > 0) return `${mins}m ${secs}s`
  return `${secs}s`
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
  const inputRef = useRef<HTMLInputElement>(null)

  const preview = useMemo(() => {
    return file ? URL.createObjectURL(file) : null
  }, [file])

  function handleFile(f: File) {
    onFile(f)
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        const f = e.dataTransfer.files?.[0]
        if (f) handleFile(f)
      }}
      className={cn(
        'group relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed border-border bg-card/20 p-6 text-center transition-all duration-300 hover:border-info/50 hover:bg-card/40 cursor-pointer',
        dragging && 'border-info bg-info/5 scale-[1.02]',
      )}
      onClick={() => { if (!preview) inputRef.current?.click() }}
    >
      {preview ? (
        <div className="flex w-full items-center justify-between gap-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-3 min-w-0">
            <img src={preview || '/placeholder.svg'} alt="Uploaded probe face" className="size-16 rounded object-cover ring-1 ring-border shadow-sm" />
            <div className="flex flex-col items-start min-w-0">
              <span className="max-w-32 truncate font-mono text-xs text-foreground font-medium">{file?.name}</span>
              <span className="text-[10px] text-muted-foreground flex items-center gap-1 mt-0.5"><Check className="size-3 text-success" /> Ready</span>
            </div>
          </div>
          <div className="flex flex-col gap-1">
             <Button size="sm" variant="outline" className="h-7 text-[10px] px-2" onClick={() => inputRef.current?.click()}>Replace</Button>
             <Button size="sm" variant="ghost" className="h-7 text-[10px] px-2 text-destructive hover:bg-destructive/10" onClick={onClear}>Clear</Button>
          </div>
        </div>
      ) : (
        <>
          <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground transition-all duration-300 group-hover:bg-info/10 group-hover:text-info">
            <UploadCloud className="size-5" />
          </span>
          <div>
            <p className="text-xs font-medium transition-colors group-hover:text-info">Upload probe image</p>
            <p className="mt-0.5 text-[10px] text-muted-foreground">JPG / PNG</p>
          </div>
        </>
      )}
      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={(e) => {
        const f = e.target.files?.[0]; if (f) handleFile(f)
      }} />
    </div>
  )
}

function Chip({ active, onClick, children, className }: { active: boolean, onClick: () => void, children: React.ReactNode, className?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors',
        active ? 'border-info/40 bg-info/15 text-info' : 'border-border bg-card/50 text-muted-foreground hover:text-foreground hover:bg-muted',
        className
      )}
    >
      {children}
    </button>
  )
}

function getRangeDates(range: string) {
  const now = new Date()
  let from = new Date()
  if (range === '1h') from.setHours(now.getHours() - 1)
  else if (range === '6h') from.setHours(now.getHours() - 6)
  else if (range === '24h') from.setHours(now.getHours() - 24)
  const format = (d: Date) => {
    const tzOffset = d.getTimezoneOffset() * 60000;
    return (new Date(d.getTime() - tzOffset)).toISOString().slice(0, 16);
  }
  return { from: format(from), to: format(now) }
}

export function ForensicTab() {
  const { data: cameras = [] } = useQuery({ queryKey: ['cameras'], queryFn: fetchCameras })
  const { data: networkData } = useQuery({ queryKey: ['movement-network'], queryFn: fetchMovementNetwork })
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const { data: unregistered = [] } = useQuery({ queryKey: ['unregistered'], queryFn: fetchUnregisteredSubjects })

  // Left Panel State
  const [searchSource, setSearchSource] = useState<'probe' | 'known'>('probe')
  const [file, setFile] = useState<File | null>(null)
  
  const [vectorSearchQuery, setVectorSearchQuery] = useState('')
  const [selectedKnownVectorId, setSelectedKnownVectorId] = useState<string | null>(null)

  const [timeRange, setTimeRange] = useState<'1h' | '6h' | '24h' | 'custom'>('24h')
  const [dateFrom, setDateFrom] = useState(() => getRangeDates('24h').from)
  const [dateTo, setDateTo] = useState(() => getRangeDates('24h').to)
  const [selectedCameras, setSelectedCameras] = useState<string[]>([])
  const [gender, setGender] = useState<Gender | 'all'>('all')

  const search = useMutation<ForensicMatch[], Error, ForensicSearchPayload>({ mutationFn: runForensicSearch })

  // Right Panel State
  const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null)
  const [activeEventIndex, setActiveEventIndex] = useState<number | null>(null)
  
  const selectedMatch = useMemo(() => {
    if (!search.data) return null;
    return search.data.find(m => m.profileId === selectedMatchId) || search.data[0] || null;
  }, [search.data, selectedMatchId])
  
  const { data: trajectory, isFetching: trajectoryLoading } = useQuery({
    queryKey: ['trajectory', selectedMatch?.profileId],
    queryFn: () => selectedMatch?.profileId ? fetchTrajectory(selectedMatch.profileId) : null,
    enabled: !!selectedMatch?.profileId,
  })

  // Effects
  useEffect(() => {
    if (timeRange !== 'custom') {
      const { from, to } = getRangeDates(timeRange)
      setDateFrom(from)
      setDateTo(to)
    }
  }, [timeRange])
  
  useEffect(() => {
    if (search.data && search.data.length > 0 && !selectedMatchId) {
      setSelectedMatchId(search.data[0].profileId || null)
    }
  }, [search.data])

  function toggleCamera(id: string) {
    if (id === 'all') { setSelectedCameras([]); return }
    setSelectedCameras((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
  }

  function handleReset() {
    setFile(null)
    setSelectedKnownVectorId(null)
    setVectorSearchQuery('')
    setTimeRange('24h')
    setSelectedCameras([])
    setGender('all')
    search.reset()
    setSelectedMatchId(null)
    setActiveEventIndex(null)
  }

  const knownVectors = useMemo(() => {
    return [
      ...profiles.map(p => ({ id: p.id, name: p.name, type: 'profile', detections: p.embeddingCount, lastSeen: p.lastSeen })),
      ...unregistered.map(u => ({ id: u.id, name: u.displayName, type: 'unregistered', detections: u.captureCount, lastSeen: u.lastSeen }))
    ]
  }, [profiles, unregistered])

  const filteredVectors = useMemo(() => {
    if (!vectorSearchQuery) return knownVectors.slice(0, 20)
    const q = vectorSearchQuery.toLowerCase()
    return knownVectors.filter(v => 
      v.name.toLowerCase().includes(q) || v.id.toLowerCase().includes(q)
    ).slice(0, 20)
  }, [knownVectors, vectorSearchQuery])

  const selectedKnownVector = useMemo(() => knownVectors.find(v => v.id === selectedKnownVectorId), [knownVectors, selectedKnownVectorId])

  // --- Network Layout logic ---
  const nodes = useMemo(() => {
    const topologyCameras = cameras.length > 0 ? cameras : []
    return topologyCameras.map((c, i) => {
      const angle = (i / Math.max(1, topologyCameras.length)) * 2 * Math.PI - Math.PI / 2
      const radius = 220
      return { id: c.id, name: c.name, x: 400 + radius * Math.cos(angle), y: 300 + radius * Math.sin(angle) }
    })
  }, [cameras])
  
  const getNodePos = (id: string) => nodes.find(n => n.id === id) || { x: 400, y: 300 }

  // --- Event Aggregation ---
  type AggregatedEvent = { type: 'first' | 'transition' | 'last', timestamp: string, fromCamera?: string, toCamera: string, elapsedMs?: number, confidence: number }
  const aggregatedEvents: AggregatedEvent[] = useMemo(() => {
    if (!trajectory?.path || trajectory.path.length === 0) return []
    const path = trajectory.path
    if (path.length === 1) {
      return [
        { type: 'first', timestamp: path[0].timestamp, toCamera: path[0].cameraId, confidence: path[0].confidence },
        { type: 'last', timestamp: path[0].timestamp, toCamera: path[0].cameraId, confidence: path[0].confidence }
      ]
    }

    const events: AggregatedEvent[] = []
    
    events.push({
      type: 'first',
      timestamp: path[0].timestamp,
      toCamera: path[0].cameraId,
      confidence: path[0].confidence
    })

    let currentCam = path[0].cameraId
    let currentCamStartTime = new Date(path[0].timestamp).getTime()

    for (let i = 1; i < path.length; i++) {
      const node = path[i]
      if (node.cameraId !== currentCam) {
        const nodeTime = new Date(node.timestamp).getTime()
        events.push({
          type: 'transition',
          timestamp: node.timestamp,
          fromCamera: currentCam,
          toCamera: node.cameraId,
          elapsedMs: nodeTime - currentCamStartTime,
          confidence: node.confidence
        })
        currentCam = node.cameraId
        currentCamStartTime = nodeTime
      }
    }

    const lastNode = path[path.length - 1]
    events.push({
      type: 'last',
      timestamp: lastNode.timestamp,
      toCamera: lastNode.cameraId,
      confidence: lastNode.confidence
    })

    return events
  }, [trajectory])

  return (
    <div className="flex h-[calc(100vh-140px)] gap-4 overflow-hidden">
      
      {/* ==================== LEFT COLUMN ==================== */}
      <div className="w-[320px] flex-shrink-0 flex flex-col gap-4 overflow-y-auto pr-1">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold tracking-wide uppercase text-foreground flex items-center gap-2">
            <ScanSearch className="size-4 text-info" /> Forensic Search
          </h2>
        </div>
        
        <Card className="flex flex-col gap-5 p-4 bg-card/60 border-border/60">
          
          <div className="space-y-2">
            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Search Source</Label>
            <div className="grid grid-cols-2 gap-1 bg-muted p-1 rounded-md">
              <button 
                className={cn("text-xs py-1.5 rounded transition-colors", searchSource === 'probe' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
                onClick={() => setSearchSource('probe')}
              >
                Probe Image
              </button>
              <button 
                className={cn("text-xs py-1.5 rounded transition-colors", searchSource === 'known' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground")}
                onClick={() => setSearchSource('known')}
              >
                Known Vector
              </button>
            </div>
          </div>

          {searchSource === 'probe' ? (
            <div className="space-y-2">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Probe Image</Label>
              <Dropzone file={file} onFile={setFile} onClear={() => setFile(null)} />
            </div>
          ) : (
            <div className="space-y-2">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Known Vector</Label>
              {!selectedKnownVector ? (
                <div className="space-y-2 relative">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                    <Input 
                      placeholder="Search known vectors..." 
                      className="pl-9 h-9 text-xs" 
                      value={vectorSearchQuery}
                      onChange={e => setVectorSearchQuery(e.target.value)}
                    />
                  </div>
                  {vectorSearchQuery.length > 0 && (
                    <div className="absolute top-10 left-0 right-0 z-50 flex flex-col gap-1 max-h-48 overflow-y-auto border border-border rounded-md p-1 bg-card shadow-lg">
                      {filteredVectors.length === 0 ? (
                        <div className="p-3 text-center text-xs text-muted-foreground">No vectors found</div>
                      ) : (
                        filteredVectors.map(v => (
                          <button 
                            key={v.id}
                            className="flex flex-col items-start p-2 rounded hover:bg-muted transition-colors text-left"
                            onClick={() => {
                              setSelectedKnownVectorId(v.id)
                              setVectorSearchQuery('')
                            }}
                          >
                            <span className="text-xs font-medium text-foreground">{v.name}</span>
                            <span className="text-[10px] font-mono text-muted-foreground truncate w-full">{v.id}</span>
                            <span className="text-[10px] text-muted-foreground mt-0.5">{v.detections} detections</span>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="border border-info/30 bg-info/5 rounded-md p-3 relative">
                  <button className="absolute top-2 right-2 text-muted-foreground hover:text-destructive" onClick={() => setSelectedKnownVectorId(null)}>
                    <X className="size-4" />
                  </button>
                  <span className="text-xs font-medium text-foreground block mb-1 uppercase tracking-wider">{selectedKnownVector.name}</span>
                  <span className="text-[10px] font-mono text-muted-foreground truncate w-[90%] block">Vector: {selectedKnownVector.id}</span>
                  <span className="text-[10px] text-muted-foreground mt-1 block">{selectedKnownVector.detections} detections</span>
                </div>
              )}
            </div>
          )}

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Date / Time</Label>
            </div>
            <div className="grid grid-cols-4 gap-1">
              {(['1h', '6h', '24h', 'custom'] as const).map(r => (
                <Chip key={r} active={timeRange === r} onClick={() => setTimeRange(r)} className="px-1 text-[10px]">
                  {r === 'custom' ? 'Custom' : `Last ${r}`}
                </Chip>
              ))}
            </div>
            {timeRange === 'custom' && (
              <div className="grid grid-cols-2 gap-2 mt-2">
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">From</Label>
                  <Input type="datetime-local" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="h-7 text-[10px] px-2" />
                </div>
                <div className="space-y-1">
                  <Label className="text-[10px] text-muted-foreground">To</Label>
                  <Input type="datetime-local" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="h-7 text-[10px] px-2" />
                </div>
              </div>
            )}
          </div>

          <div className="space-y-2">
            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Camera Nodes</Label>
            <div className="flex flex-wrap gap-1.5">
              <Chip active={selectedCameras.length === 0} onClick={() => toggleCamera('all')}>All Nodes</Chip>
              {cameras.map((c) => (
                <Chip key={c.id} active={selectedCameras.includes(c.id)} onClick={() => toggleCamera(c.id)}>{c.id}</Chip>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Gender</Label>
            <div className="flex flex-wrap gap-1.5">
              {(['all', 'male', 'female', 'unknown'] as const).map((g) => (
                <Chip key={g} active={gender === g} onClick={() => setGender(g)}><span className="capitalize">{g}</span></Chip>
              ))}
            </div>
          </div>

          <div className="pt-2 flex flex-col gap-2 border-t border-border/50">
            <Button
              onClick={() => {
                if (searchSource === 'probe' && !file) return
                if (searchSource === 'known' && !selectedKnownVectorId) return
                
                search.mutate({
                  imageFile: searchSource === 'probe' ? (file || undefined) : undefined,
                  profileId: searchSource === 'known' ? (selectedKnownVectorId || undefined) : undefined,
                  from: dateFrom,
                  to: dateTo,
                  cameraIds: selectedCameras.length > 0 ? selectedCameras : undefined,
                  gender: gender === 'all' ? undefined : gender,
                })
              }}
              disabled={(searchSource === 'probe' && !file) || (searchSource === 'known' && !selectedKnownVectorId) || search.isPending}
              className="w-full bg-info hover:bg-info/90 text-info-foreground shadow-[0_0_15px_color-mix(in_oklch,var(--color-info)_30%,transparent)]"
            >
              <ScanSearch className="mr-2 size-4" />
              {search.isPending ? 'Searching...' : 'Run Forensic Search'}
            </Button>
            <Button variant="ghost" size="sm" onClick={handleReset} className="text-muted-foreground hover:text-foreground text-xs">
              <RotateCcw className="mr-2 size-3" /> Reset Filters
            </Button>
          </div>
        </Card>
      </div>

      {/* ==================== RIGHT COLUMN ==================== */}
      <div className="flex-1 flex flex-col min-w-0 bg-background rounded-lg border border-border shadow-sm overflow-hidden">
        
        {!search.data && !search.isPending && !search.isError && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted-foreground">
            <ScanSearch className="size-16 mb-4 opacity-20" />
            <h3 className="text-lg font-medium text-foreground mb-1 uppercase tracking-wider">No Search Active</h3>
            <p className="max-w-sm text-sm">Upload a probe image or select a known vector and configure filters to begin forensic search.</p>
          </div>
        )}

        {search.isPending && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted-foreground">
            <div className="size-16 mb-4 rounded-full border-4 border-info/30 border-t-info animate-spin" />
            <h3 className="text-lg font-medium text-foreground mb-1 uppercase tracking-wider">Searching Index</h3>
            <p className="max-w-sm text-sm animate-pulse">Comparing vector against historical detections...</p>
          </div>
        )}

        {search.isError && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-destructive">
            <ScanSearch className="size-16 mb-4 opacity-50" />
            <h3 className="text-lg font-medium mb-1 uppercase tracking-wider">Search Failed</h3>
            <p className="max-w-sm text-sm">{search.error.message || 'An error occurred during forensic search.'}</p>
          </div>
        )}

        {search.data && search.data.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-muted-foreground">
            <ScanSearch className="size-16 mb-4 opacity-20" />
            <h3 className="text-lg font-medium text-foreground mb-1 uppercase tracking-wider">No Matches Found</h3>
            <p className="max-w-sm text-sm mb-6">No indexed candidates matched the selected search criteria.</p>
          </div>
        )}

        {search.data && search.data.length > 0 && (
          <div className="flex-1 flex flex-col min-h-0">
            <div className="flex items-center justify-between p-4 border-b border-border bg-card/40 shrink-0">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-semibold tracking-wide uppercase text-foreground">Matching Candidates</h2>
                <span className="bg-muted text-muted-foreground text-[10px] px-2 py-0.5 rounded font-mono">
                  {search.data.length} MATCHES
                </span>
              </div>
              
              <div className="flex items-center gap-2">
                <Label className="text-xs text-muted-foreground">Selected Candidate</Label>
                <div className="relative">
                  <select 
                    className="appearance-none bg-background border border-border rounded-md text-xs pl-3 pr-8 py-1.5 focus:outline-none focus:ring-1 focus:ring-info font-mono"
                    value={selectedMatchId || ''}
                    onChange={(e) => { setSelectedMatchId(e.target.value); setActiveEventIndex(null) }}
                  >
                    {search.data.map(m => (
                      <option key={m.profileId} value={m.profileId || ''}>
                        {m.profileName} · {formatPercentage(m.cosineSimilarity)} · {m.cameraName}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
              
              {selectedMatch && (
                <div className="flex items-center gap-6 bg-card/60 border border-border/60 rounded-lg p-4 shrink-0">
                  <FaceTile tone={selectedMatch.avatarTone} size="lg" flagged={selectedMatch.role === 'blacklist'} />
                  <div className="flex-1 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">Vector ID</span>
                      <span className="text-sm font-mono text-foreground truncate" title={selectedMatch.profileId || 'Unknown'}>{selectedMatch.profileId || 'vec_unknown'}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">Similarity</span>
                      <span className="text-sm font-mono text-info font-semibold">{formatPercentage(selectedMatch.cosineSimilarity)}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">First Detected</span>
                      <span className="text-sm font-mono text-foreground">{trajectory?.path && trajectory.path.length > 0 ? formatTime(trajectory.path[0].timestamp) : '--:--'}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">Last Detected</span>
                      <span className="text-sm font-mono text-foreground">{trajectory?.path && trajectory.path.length > 0 ? formatTime(trajectory.path[trajectory.path.length-1].timestamp) : '--:--'}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">Cameras Visited</span>
                      <span className="text-sm font-mono text-foreground">{trajectory?.path ? new Set(trajectory.path.map(p => p.cameraId)).size : 0}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-muted-foreground tracking-wider">Detections</span>
                      <span className="text-sm font-mono text-foreground">{trajectory?.path ? trajectory.path.length : 0}</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4 min-h-[400px]">
                
                <div className="flex flex-col gap-4 min-w-0">
                  
                  {/* Network Graph */}
                  <div className="flex-1 border border-border/60 bg-card/30 rounded-lg flex flex-col relative overflow-hidden min-h-[300px]">
                    <div className="absolute top-3 left-4 z-10">
                      <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                        <MonitorPlay className="size-3.5" /> Camera Movement Network
                      </h3>
                    </div>
                    
                    <div className="flex-1 relative w-full h-full">
                      <svg viewBox="0 0 800 600" className="absolute inset-0 w-full h-full" preserveAspectRatio="xMidYMid meet">
                        {networkData?.edges.map((edge, i) => {
                          const start = getNodePos(edge.fromCameraId)
                          const end = getNodePos(edge.toCameraId)
                          return (
                            <line key={`bg-${i}`} x1={start.x} y1={start.y} x2={end.x} y2={end.y} stroke="var(--muted)" strokeWidth="1" strokeDasharray="4 4" opacity={0.3} />
                          )
                        })}

                        {/* Foreground Edges based on aggregated events */}
                        {aggregatedEvents.map((ev, i) => {
                          if (ev.type !== 'transition' || !ev.fromCamera) return null;
                          const start = getNodePos(ev.fromCamera)
                          const end = getNodePos(ev.toCamera)
                          const isActive = activeEventIndex === i;
                          return (
                            <g key={`path-${i}`}>
                              <line 
                                x1={start.x} y1={start.y} x2={end.x} y2={end.y}
                                stroke={isActive ? "var(--color-info)" : "var(--color-info)"} 
                                strokeWidth={isActive ? 3 : 2} opacity={isActive ? 1 : 0.6}
                                markerEnd="url(#arrow)"
                              />
                            </g>
                          )
                        })}

                        <defs>
                          <marker id="arrow" viewBox="0 0 10 10" refX="25" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-info)" />
                          </marker>
                        </defs>

                        {nodes.map(n => {
                          const eventIndices = aggregatedEvents.reduce((acc: number[], ev, idx) => (ev.toCamera === n.id || ev.fromCamera === n.id) ? [...acc, idx] : acc, [])
                          const inPath = eventIndices.length > 0;
                          const isActive = activeEventIndex !== null && eventIndices.includes(activeEventIndex);
                          return (
                            <g 
                              key={n.id} 
                              transform={`translate(${n.x}, ${n.y})`}
                              className={cn("transition-all duration-300 cursor-pointer", isActive ? "scale-110" : "")}
                              onClick={() => { if (inPath) setActiveEventIndex(eventIndices[0]) }}
                            >
                              <circle 
                                r={16} 
                                fill={isActive ? "var(--color-info)" : inPath ? "color-mix(in oklch, var(--color-info) 20%, var(--card))" : "var(--card)"}
                                stroke={isActive ? "var(--background)" : inPath ? "var(--color-info)" : "var(--border)"}
                                strokeWidth={2}
                              />
                              <text y={28} textAnchor="middle" className={cn("text-[10px] font-mono", isActive ? "fill-info font-bold" : inPath ? "fill-foreground" : "fill-muted-foreground")}>
                                {n.id}
                              </text>
                            </g>
                          )
                        })}
                      </svg>
                    </div>
                  </div>

                  {/* Timeline */}
                  <div className="border border-border/60 bg-card/30 rounded-lg p-4 pb-6 flex flex-col gap-3 shrink-0">
                    <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                      <History className="size-3.5" /> Movement Timeline
                    </h3>
                    
                    <div className="relative h-12 w-full mt-2">
                      <div className="absolute top-1/2 left-4 right-4 h-0.5 bg-border -translate-y-1/2 rounded-full" />
                      
                      {aggregatedEvents.map((ev, i) => {
                        const pos = aggregatedEvents.length > 1 ? (i / (aggregatedEvents.length - 1)) * 100 : 50;
                        const isActive = activeEventIndex === i;
                        return (
                          <div 
                            key={`tl-${i}`}
                            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 flex flex-col items-center cursor-pointer group"
                            style={{ left: `calc(1rem + (100% - 2rem) * ${pos / 100})` }}
                            onClick={() => setActiveEventIndex(i)}
                          >
                            <div className={cn("size-3 rounded-full border-2 transition-all duration-200 z-10", isActive ? "bg-info border-background scale-125 ring-2 ring-info/30" : "bg-card border-info group-hover:bg-info/30")} />
                            <div className={cn("absolute top-4 flex flex-col items-center whitespace-nowrap transition-colors", isActive ? "text-info" : "text-muted-foreground group-hover:text-foreground")}>
                              <span className="text-[9px] font-mono">{formatTime(ev.timestamp)}</span>
                              <span className="text-[9px] font-medium">{ev.toCamera}</span>
                            </div>
                          </div>
                        )
                      })}
                      {!aggregatedEvents.length && (
                        <div className="absolute inset-0 flex items-center justify-center">
                          <span className="text-xs text-muted-foreground">No timeline events</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Event Log */}
                <div className="border border-border/60 bg-card/30 rounded-lg flex flex-col overflow-hidden">
                  <div className="p-3 border-b border-border/60 bg-card/50">
                    <h3 className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                      <Activity className="size-3.5" /> Event Log
                    </h3>
                  </div>
                  
                  <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-1">
                    {aggregatedEvents.length > 0 ? aggregatedEvents.map((ev, i) => {
                      const isActive = activeEventIndex === i;
                      const isLast = i === aggregatedEvents.length - 1;
                      return (
                        <div 
                          key={`ev-${i}`}
                          className={cn(
                            "relative flex gap-3 p-3 rounded-md transition-colors cursor-pointer border border-transparent",
                            isActive ? "bg-info/10 border-info/20" : "hover:bg-muted/50"
                          )}
                          onClick={() => setActiveEventIndex(i)}
                        >
                          {!isLast && (
                            <div className={cn("absolute left-[17px] top-[26px] bottom-[-12px] w-px", isActive ? "bg-info/50" : "bg-border")} />
                          )}
                          <div className={cn("mt-1.5 size-2.5 rounded-full shrink-0 z-10", isActive ? "bg-info shadow-[0_0_8px_var(--color-info)]" : "bg-muted-foreground")} />
                          
                          <div className="flex flex-col min-w-0 w-full">
                            <div className="flex items-center gap-2">
                              <span className={cn("font-mono text-xs", isActive ? "text-foreground font-semibold" : "text-muted-foreground")}>
                                {formatTime(ev.timestamp)}
                              </span>
                            </div>
                            
                            <p className="text-[11px] font-semibold uppercase tracking-wider text-foreground mt-1">
                              {ev.type === 'first' ? 'FIRST DETECTION' : ev.type === 'last' ? 'LAST DETECTION' : 'CAMERA TRANSITION'}
                            </p>
                            
                            {ev.type === 'transition' ? (
                              <p className="text-[11px] font-mono mt-0.5 text-muted-foreground">
                                {ev.fromCamera} <ArrowRight className="inline size-3 mx-0.5" /> {ev.toCamera}
                              </p>
                            ) : (
                              <p className="text-[11px] font-mono mt-0.5 text-muted-foreground">
                                {ev.toCamera}
                              </p>
                            )}

                            {ev.elapsedMs !== undefined && (
                              <p className="text-[10px] text-muted-foreground mt-1.5 border-t border-border/50 pt-1">
                                Elapsed: <span className="text-foreground">{formatDuration(ev.elapsedMs)}</span>
                              </p>
                            )}
                            
                            <p className="text-[10px] text-muted-foreground mt-0.5">
                              Confidence: {formatPercentage(ev.confidence)}
                            </p>
                          </div>
                        </div>
                      )
                    }) : (
                      <div className="py-8 text-center text-xs text-muted-foreground">No events available.</div>
                    )}
                  </div>
                </div>

              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
