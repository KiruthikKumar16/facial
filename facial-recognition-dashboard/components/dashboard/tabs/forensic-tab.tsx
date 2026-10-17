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
  fetchImportBatches,
  fetchFaceLogs,
  type ForensicSearchPayload,
} from '@/lib/api'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { FaceTile } from '@/components/dashboard/shared'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { ForensicMatch, Gender } from '@/lib/types'
import {
  ImageUp, ArrowRight, ScanSearch, UploadCloud, X, History, Activity, MonitorPlay, RotateCcw, Check, ChevronDown, Search,
  Film, Lock, Unlock, Clock, UserCheck, Sparkles, User
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

function toLocalDatetimeString(isoOrDate: string | Date | undefined): string {
  if (!isoOrDate) return ''
  const d = new Date(isoOrDate)
  if (isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function getRangeDates(range: string) {
  const now = new Date()
  const from = new Date()
  if (range === '1h') from.setHours(now.getHours() - 1)
  else if (range === '6h') from.setHours(now.getHours() - 6)
  else if (range === '24h') from.setHours(now.getHours() - 24)
  const format = (d: Date) => {
    const tzOffset = d.getTimezoneOffset() * 60000;
    return (new Date(d.getTime() - tzOffset)).toISOString().slice(0, 16);
  }
  return { from: format(from), to: format(now) }
}

export interface ClipVectorItem {
  id: string
  name: string
  role: string
  type: 'profile' | 'unregistered'
  thumbnail?: string | null
  sightingCount: number
  firstSeen?: string
  lastSeen?: string
  batchId?: string | null
  cameraName?: string | null
}

export function ForensicTab() {
  const { data: cameras = [] } = useQuery({ queryKey: ['cameras'], queryFn: fetchCameras })
  const { data: networkData } = useQuery({ queryKey: ['movement-network'], queryFn: fetchMovementNetwork })
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const { data: unregistered = [] } = useQuery({ queryKey: ['unregistered'], queryFn: fetchUnregisteredSubjects })
  const { data: importBatches = [] } = useQuery({ queryKey: ['import-batches'], queryFn: fetchImportBatches })
  const { data: archiveLogs = [] } = useQuery({
    queryKey: ['archive-logs-forensic'],
    queryFn: () => fetchFaceLogs(300, 0, 'archive'),
  })

  // Left Panel State
  const [searchSource, setSearchSource] = useState<'clip' | 'known' | 'probe'>('clip')
  const [file, setFile] = useState<File | null>(null)
  
  // Clip & Batch Selection State
  const [selectedBatchId, setSelectedBatchId] = useState<string>('all')
  const [isTimeLocked, setIsTimeLocked] = useState<boolean>(false)
  const [isVectorDropdownOpen, setIsVectorDropdownOpen] = useState<boolean>(false)
  const [dropdownSearch, setDropdownSearch] = useState<string>('')
  const dropdownRef = useRef<HTMLDivElement>(null)

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
  
  const { data: trajectory } = useQuery({
    queryKey: ['trajectory', selectedMatch?.profileId],
    queryFn: () => selectedMatch?.profileId ? fetchTrajectory(selectedMatch.profileId) : null,
    enabled: !!selectedMatch?.profileId,
  })

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsVectorDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Effects
  useEffect(() => {
    if (timeRange !== 'custom' && !isTimeLocked) {
      const { from, to } = getRangeDates(timeRange)
      setDateFrom(from)
      setDateTo(to)
    }
  }, [timeRange, isTimeLocked])
  
  useEffect(() => {
    if (search.data && search.data.length > 0 && !selectedMatchId) {
      setSelectedMatchId(search.data[0].profileId || null)
    }
  }, [search.data, selectedMatchId])

  function toggleCamera(id: string) {
    if (id === 'all') { setSelectedCameras([]); return }
    setSelectedCameras((prev) => prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id])
  }

  function handleReset() {
    setFile(null)
    setSelectedKnownVectorId(null)
    setVectorSearchQuery('')
    setDropdownSearch('')
    setTimeRange('24h')
    setIsTimeLocked(false)
    setSelectedCameras([])
    setGender('all')
    search.reset()
    setSelectedMatchId(null)
    setActiveEventIndex(null)
  }

  // Clip recognized vectors aggregation
  const clipVectors = useMemo<ClipVectorItem[]>(() => {
    const list: ClipVectorItem[] = []
    const rawDets = archiveLogs || []

    // 1. Unregistered Subjects from footage
    unregistered.forEach(u => {
      const subjectDets = rawDets.filter(d => (d as any).unregisteredSubjectId === u.id)
      const bestThumb = u.thumbnail || subjectDets[0]?.faceImage || null
      const count = subjectDets.length > 0 ? subjectDets.length : (u.captureCount || 1)
      const firstSeen = subjectDets[0]?.timestamp || u.firstSeen
      const lastSeen = subjectDets[subjectDets.length - 1]?.timestamp || u.lastSeen
      const batchId = subjectDets[0]?.batchId || null
      const cam = subjectDets[0]?.cameraName || null

      if (selectedBatchId === 'all' || !batchId || batchId === selectedBatchId) {
        list.push({
          id: u.id,
          name: u.displayName || `Subject ${u.id.slice(0, 8)}`,
          role: 'visitor',
          type: 'unregistered',
          thumbnail: bestThumb,
          sightingCount: count,
          firstSeen,
          lastSeen,
          batchId,
          cameraName: cam,
        })
      }
    })

    // 2. Profiles (Enrolled staff, VIPs with footage sightings or active enrollments)
    profiles.forEach(p => {
      const pDets = rawDets.filter(d => d.profileId === p.id)
      const bestThumb = pDets[0]?.faceImage || null
      const count = pDets.length > 0 ? pDets.length : (p.embeddingCount || 0)
      const firstSeen = pDets[0]?.timestamp || (p.lastSeen ? String(p.lastSeen) : undefined)
      const lastSeen = pDets[pDets.length - 1]?.timestamp || (p.lastSeen ? String(p.lastSeen) : undefined)
      const batchId = pDets[0]?.batchId || null
      const cam = pDets[0]?.cameraName || null

      if (selectedBatchId === 'all' || pDets.length > 0 || !batchId || batchId === selectedBatchId) {
        list.push({
          id: p.id,
          name: p.name,
          role: p.role || 'visitor',
          type: 'profile',
          thumbnail: bestThumb,
          sightingCount: count,
          firstSeen,
          lastSeen,
          batchId,
          cameraName: cam,
        })
      }
    })

    return list.sort((a, b) => b.sightingCount - a.sightingCount)
  }, [unregistered, profiles, archiveLogs, selectedBatchId])

  const filteredClipVectors = useMemo(() => {
    if (!dropdownSearch) return clipVectors
    const q = dropdownSearch.toLowerCase()
    return clipVectors.filter(v =>
      v.name.toLowerCase().includes(q) || v.id.toLowerCase().includes(q) || v.role.toLowerCase().includes(q)
    )
  }, [clipVectors, dropdownSearch])

  const selectedClipVector = useMemo(() => {
    return clipVectors.find(v => v.id === selectedKnownVectorId) || null
  }, [clipVectors, selectedKnownVectorId])

  const handleSelectClipVector = (v: ClipVectorItem) => {
    setSelectedKnownVectorId(v.id)
    setIsVectorDropdownOpen(false)

    // If time is not locked, auto-sync to this vector's recorded time window!
    if (!isTimeLocked) {
      if (v.firstSeen && v.lastSeen) {
        const start = new Date(v.firstSeen)
        const end = new Date(v.lastSeen)
        const fromDate = new Date(start.getTime() - 5 * 60 * 1000)
        const toDate = new Date(end.getTime() + 5 * 60 * 1000)
        setDateFrom(toLocalDatetimeString(fromDate))
        setDateTo(toLocalDatetimeString(toDate))
        setTimeRange('custom')
      } else {
        const batch = importBatches.find(b => b.id === (v.batchId || selectedBatchId))
        if (batch?.footageStart && batch?.footageEnd) {
          setDateFrom(toLocalDatetimeString(batch.footageStart))
          setDateTo(toLocalDatetimeString(batch.footageEnd))
          setTimeRange('custom')
        }
      }
    }
  }

  const applyTimePreset = (preset: 'clip' | '15m' | '1h' | '24h') => {
    const curFrom = dateFrom ? new Date(dateFrom) : new Date()

    if (preset === 'clip') {
      const batch = importBatches.find(b => b.id === selectedBatchId) || importBatches[0]
      if (batch?.footageStart && batch?.footageEnd) {
        setDateFrom(toLocalDatetimeString(batch.footageStart))
        setDateTo(toLocalDatetimeString(batch.footageEnd))
        setTimeRange('custom')
        return
      }
      if (selectedClipVector?.firstSeen && selectedClipVector?.lastSeen) {
        setDateFrom(toLocalDatetimeString(selectedClipVector.firstSeen))
        setDateTo(toLocalDatetimeString(selectedClipVector.lastSeen))
        setTimeRange('custom')
        return
      }
    } else if (preset === '15m') {
      const center = selectedClipVector?.firstSeen ? new Date(selectedClipVector.firstSeen) : curFrom
      const f = new Date(center.getTime() - 15 * 60 * 1000)
      const t = new Date(center.getTime() + 15 * 60 * 1000)
      setDateFrom(toLocalDatetimeString(f))
      setDateTo(toLocalDatetimeString(t))
      setTimeRange('custom')
      return
    } else if (preset === '1h') {
      const center = selectedClipVector?.firstSeen ? new Date(selectedClipVector.firstSeen) : curFrom
      const f = new Date(center.getTime() - 60 * 60 * 1000)
      const t = new Date(center.getTime() + 60 * 60 * 1000)
      setDateFrom(toLocalDatetimeString(f))
      setDateTo(toLocalDatetimeString(t))
      setTimeRange('custom')
      return
    } else if (preset === '24h') {
      const { from, to } = getRangeDates('24h')
      setDateFrom(from)
      setDateTo(to)
      setTimeRange('24h')
    }
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
            <div className="grid grid-cols-3 gap-1 bg-muted p-1 rounded-md">
              <button 
                type="button"
                className={cn(
                  "text-xs py-1.5 rounded transition-colors font-medium flex items-center justify-center gap-1",
                  searchSource === 'clip' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
                onClick={() => setSearchSource('clip')}
              >
                <Film className="size-3" /> Clip Vectors
              </button>
              <button 
                type="button"
                className={cn(
                  "text-xs py-1.5 rounded transition-colors font-medium flex items-center justify-center gap-1",
                  searchSource === 'known' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
                onClick={() => setSearchSource('known')}
              >
                <User className="size-3" /> Gallery
              </button>
              <button 
                type="button"
                className={cn(
                  "text-xs py-1.5 rounded transition-colors font-medium flex items-center justify-center gap-1",
                  searchSource === 'probe' ? "bg-background shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"
                )}
                onClick={() => setSearchSource('probe')}
              >
                <ImageUp className="size-3" /> Probe
              </button>
            </div>
          </div>

          {/* 1. Clip / Ingested Vectors Selector */}
          {searchSource === 'clip' && (
            <div className="space-y-3">
              {/* Batch / Clip Selector */}
              <div className="space-y-1.5">
                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <Film className="size-3 text-info" /> CCTV Clip / Batch
                  </span>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    {importBatches.length} {importBatches.length === 1 ? 'batch' : 'batches'}
                  </span>
                </Label>
                <div className="relative">
                  <select
                    value={selectedBatchId}
                    onChange={(e) => setSelectedBatchId(e.target.value)}
                    className="w-full bg-background border border-border rounded-md text-xs pl-3 pr-8 py-2 text-foreground focus:outline-none focus:ring-1 focus:ring-info font-medium"
                  >
                    <option value="all">All Ingested Footage ({clipVectors.length} vectors)</option>
                    {importBatches.map(b => (
                      <option key={b.id} value={b.id}>
                        {b.name} ({b.totalDetections} detections)
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
                </div>
              </div>

              {/* Recognized Vectors in Clip Dropdown */}
              <div className="space-y-1.5 relative" ref={dropdownRef}>
                <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <UserCheck className="size-3 text-info" /> Recognized Vectors
                  </span>
                  <span className="text-[10px] text-info font-mono">
                    {filteredClipVectors.length} in clip
                  </span>
                </Label>

                {/* Dropdown Trigger */}
                <button
                  type="button"
                  onClick={() => setIsVectorDropdownOpen(!isVectorDropdownOpen)}
                  className="w-full flex items-center justify-between gap-2 p-2 bg-background border border-border rounded-md hover:border-info/50 transition-colors text-left"
                >
                  {selectedClipVector ? (
                    <div className="flex items-center gap-2.5 min-w-0">
                      {selectedClipVector.thumbnail ? (
                        <img
                          src={selectedClipVector.thumbnail.startsWith('data:') ? selectedClipVector.thumbnail : `data:image/jpeg;base64,${selectedClipVector.thumbnail}`}
                          alt={selectedClipVector.name}
                          className="size-7 rounded object-cover ring-1 ring-info/50 shrink-0"
                        />
                      ) : (
                        <div className="size-7 rounded bg-muted flex items-center justify-center shrink-0">
                          <User className="size-3.5 text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex flex-col min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-semibold text-foreground truncate">{selectedClipVector.name}</span>
                          <span className={cn(
                            "text-[8px] px-1 rounded font-mono uppercase",
                            selectedClipVector.role === 'vip' ? "bg-amber-500/10 text-amber-400 border border-amber-500/30" :
                            selectedClipVector.role === 'employee' ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" :
                            "bg-muted text-muted-foreground"
                          )}>
                            {selectedClipVector.role}
                          </span>
                        </div>
                        <span className="text-[10px] text-muted-foreground font-mono">
                          {selectedClipVector.sightingCount} sightings in clip
                        </span>
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">Select recognized vector from clip...</span>
                  )}
                  <ChevronDown className={cn("size-3.5 text-muted-foreground transition-transform shrink-0", isVectorDropdownOpen && "rotate-180")} />
                </button>

                {/* Dropdown Menu */}
                {isVectorDropdownOpen && (
                  <div className="absolute top-full left-0 right-0 z-50 mt-1 flex flex-col max-h-64 overflow-y-auto border border-border rounded-md bg-card shadow-2xl p-1.5">
                    <div className="p-1 mb-1 relative sticky top-0 bg-card z-10 border-b border-border/50">
                      <Search className="absolute left-2.5 top-2.5 size-3.5 text-muted-foreground" />
                      <Input
                        placeholder="Search persons in clip..."
                        value={dropdownSearch}
                        onChange={(e) => setDropdownSearch(e.target.value)}
                        className="pl-8 h-7 text-xs bg-background"
                        autoFocus
                      />
                    </div>

                    {filteredClipVectors.length === 0 ? (
                      <div className="p-3 text-center text-xs text-muted-foreground">
                        No vectors found matching &quot;{dropdownSearch}&quot;
                      </div>
                    ) : (
                      <div className="flex flex-col gap-0.5">
                        {filteredClipVectors.map(v => (
                          <button
                            key={v.id}
                            type="button"
                            onClick={() => handleSelectClipVector(v)}
                            className={cn(
                              "flex items-center gap-2 p-1.5 rounded hover:bg-muted transition-colors text-left",
                              selectedKnownVectorId === v.id && "bg-info/10 border border-info/30"
                            )}
                          >
                            {v.thumbnail ? (
                              <img
                                src={v.thumbnail.startsWith('data:') ? v.thumbnail : `data:image/jpeg;base64,${v.thumbnail}`}
                                alt={v.name}
                                className="size-7 rounded object-cover ring-1 ring-border shrink-0"
                              />
                            ) : (
                              <div className="size-7 rounded bg-muted flex items-center justify-center shrink-0">
                                <User className="size-3.5 text-muted-foreground" />
                              </div>
                            )}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-medium text-foreground truncate">{v.name}</span>
                                <span className={cn(
                                  "text-[8px] px-1 rounded font-mono uppercase",
                                  v.role === 'vip' ? "bg-amber-500/10 text-amber-400" :
                                  v.role === 'employee' ? "bg-emerald-500/10 text-emerald-400" :
                                  "bg-muted text-muted-foreground"
                                )}>
                                  {v.role}
                                </span>
                              </div>
                              <div className="flex items-center justify-between text-[10px] text-muted-foreground mt-0.5">
                                <span>{v.sightingCount} sightings</span>
                                {v.firstSeen && (
                                  <span className="font-mono text-[9px]">{formatTime(v.firstSeen)}</span>
                                )}
                              </div>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Selected Vector Summary Probe Card */}
              {selectedClipVector && (
                <div className="border border-info/40 bg-info/5 rounded-lg p-2.5 relative flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-info flex items-center gap-1">
                      <Sparkles className="size-3" /> Active Forensic Probe Vector
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedKnownVectorId(null)}
                      className="text-muted-foreground hover:text-destructive text-xs"
                      title="Clear probe vector"
                    >
                      <X className="size-3" />
                    </button>
                  </div>
                  <div className="flex items-center gap-2.5">
                    {selectedClipVector.thumbnail && (
                      <img
                        src={selectedClipVector.thumbnail.startsWith('data:') ? selectedClipVector.thumbnail : `data:image/jpeg;base64,${selectedClipVector.thumbnail}`}
                        alt={selectedClipVector.name}
                        className="size-11 rounded-md object-cover ring-2 ring-info/50 shadow shrink-0"
                      />
                    )}
                    <div className="flex flex-col min-w-0">
                      <span className="text-xs font-bold text-foreground truncate">{selectedClipVector.name}</span>
                      <span className="text-[10px] font-mono text-muted-foreground truncate">{selectedClipVector.id}</span>
                      <span className="text-[10px] text-emerald-400 flex items-center gap-1 mt-0.5 font-medium">
                        <Check className="size-2.5 text-emerald-400" /> 512-D Vector Ready
                      </span>
                    </div>
                  </div>
                  {selectedClipVector.firstSeen && (
                    <div className="pt-1.5 border-t border-border/40 flex items-center justify-between text-[10px]">
                      <span className="text-muted-foreground font-mono">
                        Seen: {formatTime(selectedClipVector.firstSeen)} → {formatTime(selectedClipVector.lastSeen || selectedClipVector.firstSeen)}
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          if (selectedClipVector.firstSeen && selectedClipVector.lastSeen) {
                            const start = new Date(selectedClipVector.firstSeen)
                            const end = new Date(selectedClipVector.lastSeen)
                            const fromDate = new Date(start.getTime() - 5 * 60 * 1000)
                            const toDate = new Date(end.getTime() + 5 * 60 * 1000)
                            setDateFrom(toLocalDatetimeString(fromDate))
                            setDateTo(toLocalDatetimeString(toDate))
                            setTimeRange('custom')
                          }
                        }}
                        className="text-info hover:underline font-medium"
                      >
                        Snap Time Window
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 2. Known Gallery Vector Search */}
          {searchSource === 'known' && (
            <div className="space-y-2">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Enrolled Gallery Vector</Label>
              {!selectedKnownVector ? (
                <div className="space-y-2 relative">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
                    <Input 
                      placeholder="Search gallery vectors..." 
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

          {/* 3. Probe Image Upload */}
          {searchSource === 'probe' && (
            <div className="space-y-2">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">Probe Image</Label>
              <Dropzone file={file} onFile={setFile} onClear={() => setFile(null)} />
            </div>
          )}

          {/* Time Window with Lock & Dynamic Presets */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <Label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
                <Clock className="size-3 text-info" /> Time Window
              </Label>
              <button
                type="button"
                onClick={() => setIsTimeLocked(!isTimeLocked)}
                className={cn(
                  "text-[10px] px-2 py-0.5 rounded flex items-center gap-1 border transition-colors",
                  isTimeLocked 
                    ? "border-amber-500/50 bg-amber-500/15 text-amber-400 font-medium" 
                    : "border-border text-muted-foreground hover:text-foreground"
                )}
                title={isTimeLocked ? "Time window is locked: switching vectors keeps this exact time" : "Time window auto-syncs when switching vectors"}
              >
                {isTimeLocked ? <Lock className="size-2.5 text-amber-400" /> : <Unlock className="size-2.5" />}
                {isTimeLocked ? "Locked" : "Unlocked"}
              </button>
            </div>

            <div className="grid grid-cols-4 gap-1">
              <Chip active={false} onClick={() => applyTimePreset('clip')} className="px-1 text-[10px]">
                Clip Span
              </Chip>
              <Chip active={false} onClick={() => applyTimePreset('15m')} className="px-1 text-[10px]">
                ±15m
              </Chip>
              <Chip active={false} onClick={() => applyTimePreset('1h')} className="px-1 text-[10px]">
                ±1 Hour
              </Chip>
              <Chip active={timeRange === '24h'} onClick={() => applyTimePreset('24h')} className="px-1 text-[10px]">
                Last 24h
              </Chip>
            </div>

            <div className="grid grid-cols-2 gap-2 mt-1">
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground flex items-center justify-between">
                  <span>From</span>
                  {isTimeLocked && <Lock className="size-2 text-amber-400" />}
                </Label>
                <Input
                  type="datetime-local"
                  value={dateFrom}
                  onChange={(e) => { setDateFrom(e.target.value); setTimeRange('custom') }}
                  className="h-7 text-[10px] px-2 font-mono"
                />
              </div>
              <div className="space-y-1">
                <Label className="text-[10px] text-muted-foreground flex items-center justify-between">
                  <span>To</span>
                  {isTimeLocked && <Lock className="size-2 text-amber-400" />}
                </Label>
                <Input
                  type="datetime-local"
                  value={dateTo}
                  onChange={(e) => { setDateTo(e.target.value); setTimeRange('custom') }}
                  className="h-7 text-[10px] px-2 font-mono"
                />
              </div>
            </div>

            {/* Scope Summary Badge */}
            <div className="flex items-center justify-between text-[10px] text-muted-foreground bg-muted/40 px-2 py-1 rounded border border-border/40">
              <span className="truncate font-mono">
                {dateFrom ? dateFrom.replace('T', ' ') : '--'} → {dateTo ? dateTo.replace('T', ' ') : '--'}
              </span>
              <span className={cn("text-[9px] font-mono shrink-0 ml-1 font-medium", isTimeLocked ? "text-amber-400" : "text-info")}>
                {isTimeLocked ? "🔒 LOCKED" : "⚡ AUTO"}
              </span>
            </div>
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
                if ((searchSource === 'known' || searchSource === 'clip') && !selectedKnownVectorId) return
                
                search.mutate({
                  imageFile: searchSource === 'probe' ? (file || undefined) : undefined,
                  profileId: (searchSource === 'known' || searchSource === 'clip') ? (selectedKnownVectorId || undefined) : undefined,
                  from: dateFrom,
                  to: dateTo,
                  cameraIds: selectedCameras.length > 0 ? selectedCameras : undefined,
                  gender: gender === 'all' ? undefined : gender,
                })
              }}
              disabled={(searchSource === 'probe' && !file) || ((searchSource === 'known' || searchSource === 'clip') && !selectedKnownVectorId) || search.isPending}
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
