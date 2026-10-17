'use client'

import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchFaceLogs,
  fetchImportBatches,
  fetchProfiles,
  mergeUnregisteredSubjects,
  renameUnregisteredSubject,
  assignUnregisteredSubject,
  transferSightings,
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
  FaceTile,
  ConfidenceMeter,
  StatusBadge,
  SectionHeading,
  RoleBadge,
} from '@/components/dashboard/shared'
import { formatTime, formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { DetectionStatus, FaceLog, ProfileRole } from '@/lib/types'
import { useDashboardMode } from '@/lib/mode-context'
import {
  ScanFace,
  Search,
  Users,
  HardDrive,
  Workflow,
  ChevronLeft,
  ChevronRight,
  Route,
  Database,
  Eye,
  CheckCircle2,
  AlertTriangle,
  Film,
  Clock,
  Layers,
  Sparkles,
  X,
  UserCheck,
  GitMerge,
  ArrowRight,
  Loader2,
  Check,
  Edit3,
} from 'lucide-react'
import { LineageDrawer } from '@/components/dashboard/lineage-drawer'

const PAGE_SIZE = 12

export interface UniquePerson {
  key: string
  name: string
  role: ProfileRole | null
  totalSightings: number
  bestLog: FaceLog
  allLogs: FaceLog[]
  cameras: string[]
  sourceVideos: string[]
  firstSeen: string
  lastSeen: string
  firstElapsedSec: number | null
  lastElapsedSec: number | null
  maxConfidence: number
  avgConfidence: number
  status: DetectionStatus
}

export function CctvPersonsTab({
  onNavigateToForensic,
}: {
  onNavigateToForensic?: (subjectName?: string) => void
}) {
  const queryClient = useQueryClient()
  const { selectedBatchId, setSelectedBatchId } = useDashboardMode()
  const [viewMode, setViewMode] = useState<'unique' | 'all'>('unique')
  const [statusFilter, setStatusFilter] = useState<'all' | DetectionStatus>('all')
  const [minConfidenceFilter, setMinConfidenceFilter] = useState<number>(0)
  const [minSightingsFilter, setMinSightingsFilter] = useState<number>(1)
  const [showTransientNoise, setShowTransientNoise] = useState<boolean>(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [page, setPage] = useState(0)
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)
  const [showRosterModal, setShowRosterModal] = useState(false)
  const [activeSightingsPerson, setActiveSightingsPerson] = useState<UniquePerson | null>(null)

  // Merge Selection State
  const [selectedPersonKeys, setSelectedPersonKeys] = useState<string[]>([])
  const [mergeModalOpen, setMergeModalOpen] = useState(false)
  const [mergeSourcePerson, setMergeSourcePerson] = useState<UniquePerson | null>(null)
  const [mergeTargetKey, setMergeTargetKey] = useState<string>('')
  const [isMerging, setIsMerging] = useState(false)
  const [mergeNotification, setMergeNotification] = useState<string | null>(null)

  // Rename & Assign Identity State
  const [renameTargetPerson, setRenameTargetPerson] = useState<UniquePerson | null>(null)
  const [customNameInput, setCustomNameInput] = useState('')
  const [isRenaming, setIsRenaming] = useState(false)

  // Transfer Sighting State
  const [transferSightingLog, setTransferSightingLog] = useState<FaceLog | null>(null)
  const [transferTargetKey, setTransferTargetKey] = useState<string>('')
  const [isTransferring, setIsTransferring] = useState(false)

  // Fetch batches
  const { data: batches = [] } = useQuery({
    queryKey: ['video-audit-batches'],
    queryFn: fetchImportBatches,
    refetchInterval: 5000,
  })

  // Fetch face detections from archive video
  const { data: rawLogs = [], isLoading } = useQuery({
    queryKey: ['face-logs', 'archive', selectedBatchId],
    queryFn: () => fetchFaceLogs(300, 0, 'archive', selectedBatchId ?? undefined),
    refetchInterval: 4000,
  })

  // Fetch enrolled roster for reference & 1-click assignment
  const { data: enrolledProfiles = [] } = useQuery({
    queryKey: ['profiles-reference'],
    queryFn: fetchProfiles,
  })

  // Sort profiles to highlight jenisha, selvi, pravin first
  const knownProfiles = useMemo(() => {
    const priority = ['selvi', 'pravin', 'jenisha']
    const sorted = [...enrolledProfiles]
    sorted.sort((a, b) => {
      const aPrio = priority.indexOf(a.name.toLowerCase())
      const bPrio = priority.indexOf(b.name.toLowerCase())
      if (aPrio !== -1 && bPrio !== -1) return aPrio - bPrio
      if (aPrio !== -1) return -1
      if (bPrio !== -1) return 1
      return a.name.localeCompare(b.name)
    })
    return sorted
  }, [enrolledProfiles])

  // Group raw detections into Unique Persons
  const uniquePersons = useMemo(() => {
    const map = new Map<string, FaceLog[]>()

    rawLogs.forEach((log) => {
      // Prioritize profileName (e.g. Person 1..X or enrolled employee name)
      const key = log.profileName || (log.profileId ? `Person-${log.profileId.slice(0, 6)}` : `Person-${log.id.slice(0, 6)}`)
      if (!map.has(key)) {
        map.set(key, [])
      }
      map.get(key)!.push(log)
    })

    const list: UniquePerson[] = []
    map.forEach((logs, key) => {
      // Sort chronologically
      logs.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

      // Pick best face crop (has image and highest confidence)
      const logsWithImage = logs.filter((l) => !!l.faceImage)
      const pool = logsWithImage.length > 0 ? logsWithImage : logs
      const bestLog = pool.reduce((best, cur) => (cur.confidence > best.confidence ? cur : best), pool[0])

      const cameras = Array.from(new Set(logs.map((l) => l.cameraName || l.cameraId).filter(Boolean)))
      const sourceVideos = Array.from(new Set(logs.map((l) => l.sourceVideo).filter(Boolean))) as string[]

      const elapsedSecs = logs.map((l) => l.videoElapsedSec).filter((s): s is number => s != null)
      const firstElapsedSec = elapsedSecs.length > 0 ? Math.min(...elapsedSecs) : null
      const lastElapsedSec = elapsedSecs.length > 0 ? Math.max(...elapsedSecs) : null

      const confidences = logs.map((l) => l.confidence)
      const maxConfidence = Math.max(...confidences)
      const avgConfidence = Math.round(confidences.reduce((a, b) => a + b, 0) / confidences.length)

      const hasFlagged = logs.some((l) => l.status === 'flagged')
      const hasRecognized = logs.some((l) => l.status === 'recognized')
      const status: DetectionStatus = hasFlagged ? 'flagged' : hasRecognized ? 'recognized' : 'unknown'

      list.push({
        key,
        name: key,
        role: bestLog.role,
        totalSightings: logs.length,
        bestLog,
        allLogs: logs,
        cameras,
        sourceVideos,
        firstSeen: logs[0].timestamp,
        lastSeen: logs[logs.length - 1].timestamp,
        firstElapsedSec,
        lastElapsedSec,
        maxConfidence,
        avgConfidence,
        status,
      })
    })

    // Natural numeric sort: Person 1, Person 2, ... Person 10, Person 11
    list.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))
    return list
  }, [rawLogs])

  // Filter Unique Persons
  const filteredUniquePersons = useMemo(() => {
    return uniquePersons.filter((p) => {
      if (statusFilter !== 'all' && p.status !== statusFilter) return false
      // Filter out isolated transient noise (1 sighting with < 48% confidence or Transient label)
      const isTransientNoise = (p.name.startsWith('Transient ') || p.name.startsWith('Person-')) && p.totalSightings < 2
      if (!showTransientNoise && isTransientNoise && statusFilter === 'all' && minConfidenceFilter === 0 && minSightingsFilter === 1) {
        return false
      }
      if (p.totalSightings < minSightingsFilter) return false
      if (minConfidenceFilter > 0 && p.maxConfidence < minConfidenceFilter) return false
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        return (
          p.name.toLowerCase().includes(q) ||
          p.cameras.some((c) => c.toLowerCase().includes(q)) ||
          p.sourceVideos.some((v) => v.toLowerCase().includes(q))
        )
      }
      return true
    })
  }, [uniquePersons, statusFilter, minSightingsFilter, minConfidenceFilter, showTransientNoise, searchQuery])

  // Filter raw detections for "All Sightings" view
  const filteredRawLogs = useMemo(() => {
    return rawLogs.filter((l) => {
      if (statusFilter !== 'all' && l.status !== statusFilter) return false
      if (minConfidenceFilter > 0 && l.confidence < minConfidenceFilter) return false
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        return (
          l.id.toLowerCase().includes(q) ||
          l.cameraName.toLowerCase().includes(q) ||
          l.cameraId.toLowerCase().includes(q) ||
          (l.profileName && l.profileName.toLowerCase().includes(q))
        )
      }
      return true
    })
  }, [rawLogs, statusFilter, minConfidenceFilter, searchQuery])

  // Aggregated subject counts
  const stats = useMemo(() => {
    const totalSightings = rawLogs.length
    const activePersons = uniquePersons.filter(
      (p) => p.status === 'recognized' || p.status === 'flagged' || (!p.name.startsWith('Transient ') && !p.name.startsWith('Person-')) || p.totalSightings >= 2
    )
    const uniquePersonsCount = showTransientNoise ? uniquePersons.length : activePersons.length
    const uniqueRecognized = uniquePersons.filter((p) => p.status === 'recognized').length
    const uniqueUnregistered = showTransientNoise
      ? uniquePersons.filter((p) => p.status === 'unknown').length
      : activePersons.filter((p) => p.status === 'unknown').length
    const flaggedCount = rawLogs.filter((l) => l.status === 'flagged').length

    return {
      totalSightings,
      uniquePersonsCount,
      uniqueRecognized,
      uniqueUnregistered,
      flaggedCount,
    }
  }, [rawLogs, uniquePersons, showTransientNoise])

  // Pagination depending on view mode
  const currentTotal = viewMode === 'unique' ? filteredUniquePersons.length : filteredRawLogs.length
  const pageCount = Math.ceil(currentTotal / PAGE_SIZE)
  const uniqueRows = filteredUniquePersons.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const rawRows = filteredRawLogs.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // Toggle selection for a person
  const togglePersonSelection = (key: string) => {
    setSelectedPersonKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  // Select all on current page
  const toggleSelectAllCurrentPage = () => {
    const pageKeys = uniqueRows.map((r) => r.key)
    const allSelected = pageKeys.every((k) => selectedPersonKeys.includes(k))
    if (allSelected) {
      setSelectedPersonKeys((prev) => prev.filter((k) => !pageKeys.includes(k)))
    } else {
      setSelectedPersonKeys((prev) => Array.from(new Set([...prev, ...pageKeys])))
    }
  }

  // Open merge modal for selected persons
  const handleOpenMergeSelected = () => {
    if (selectedPersonKeys.length < 2) return
    // Default primary target to the first selected person with the most sightings
    const selectedPersons = uniquePersons.filter((p) => selectedPersonKeys.includes(p.key))
    selectedPersons.sort((a, b) => b.totalSightings - a.totalSightings)
    setMergeTargetKey(selectedPersons[0]?.key || '')
    setMergeSourcePerson(null)
    setMergeModalOpen(true)
  }

  // Open merge modal for a single person row
  const handleOpenMergeSingle = (source: UniquePerson) => {
    setMergeSourcePerson(source)
    // Default target to Person 1 or the first other person
    const otherPersons = uniquePersons.filter((p) => p.key !== source.key)
    setMergeTargetKey(otherPersons[0]?.key || '')
    setMergeModalOpen(true)
  }

  // Execute Merge Operation
  const handleExecuteMerge = async () => {
    if (!mergeTargetKey) return
    setIsMerging(true)
    try {
      const targetPerson = uniquePersons.find((p) => p.key === mergeTargetKey)
      if (!targetPerson) throw new Error('Target person not found')

      const targetId = targetPerson.bestLog.profileId || targetPerson.name

      let sourcesToMerge: UniquePerson[] = []
      if (mergeSourcePerson) {
        sourcesToMerge = [mergeSourcePerson]
      } else {
        sourcesToMerge = uniquePersons.filter(
          (p) => selectedPersonKeys.includes(p.key) && p.key !== mergeTargetKey
        )
      }

      if (sourcesToMerge.length === 0) {
        throw new Error('No source persons to merge')
      }

      for (const src of sourcesToMerge) {
        const sourceId = src.bestLog.profileId || src.name
        await mergeUnregisteredSubjects(targetId, sourceId)
      }

      // Invalidate queries to refresh table and counts
      await queryClient.invalidateQueries({ queryKey: ['face-logs'] })

      const msg = `Successfully merged ${sourcesToMerge.map((s) => s.name).join(', ')} into ${targetPerson.name}. All footage sightings consolidated.`
      setMergeNotification(msg)
      setTimeout(() => setMergeNotification(null), 7000)

      setSelectedPersonKeys([])
      setMergeModalOpen(false)
      setMergeSourcePerson(null)
    } catch (err) {
      console.error('Merge failed:', err)
      alert(`Merge operation failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsMerging(false)
    }
  }

  // 1-Click Assign to Enrolled Profile
  const handleAssignToProfile = async (profileId: string, profileName: string) => {
    if (!renameTargetPerson) return
    setIsRenaming(true)
    try {
      const sourceId = renameTargetPerson.bestLog.profileId || renameTargetPerson.name
      await assignUnregisteredSubject(sourceId, profileId)
      await queryClient.invalidateQueries({ queryKey: ['face-logs'] })
      await queryClient.invalidateQueries({ queryKey: ['unregistered-subjects'] })

      const msg = `Successfully assigned ${renameTargetPerson.name} to ${profileName}! Status updated to Recognized with live profile linking.`
      setMergeNotification(msg)
      setTimeout(() => setMergeNotification(null), 8000)

      setRenameTargetPerson(null)
      if (activeSightingsPerson?.key === renameTargetPerson.key) {
        setActiveSightingsPerson(null)
      }
    } catch (err) {
      console.error('Assign failed:', err)
      alert(`Assign operation failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsRenaming(false)
    }
  }

  // Custom Display Name Rename
  const handleCustomRename = async () => {
    if (!renameTargetPerson || !customNameInput.trim()) return
    setIsRenaming(true)
    try {
      const sourceId = renameTargetPerson.bestLog.profileId || renameTargetPerson.name
      await renameUnregisteredSubject(sourceId, customNameInput.trim())
      await queryClient.invalidateQueries({ queryKey: ['face-logs'] })
      await queryClient.invalidateQueries({ queryKey: ['unregistered-subjects'] })

      const msg = `Renamed ${renameTargetPerson.name} to "${customNameInput.trim()}". Updated across all footage sightings.`
      setMergeNotification(msg)
      setTimeout(() => setMergeNotification(null), 7000)

      setRenameTargetPerson(null)
      if (activeSightingsPerson?.key === renameTargetPerson.key) {
        setActiveSightingsPerson(null)
      }
    } catch (err) {
      console.error('Rename failed:', err)
      alert(`Rename operation failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsRenaming(false)
    }
  }

  // Transfer Single Sighting to Another Person or Profile
  const handleExecuteTransferSighting = async () => {
    if (!transferSightingLog || !transferTargetKey) return
    setIsTransferring(true)
    try {
      await transferSightings([transferSightingLog.id], transferTargetKey)
      await queryClient.invalidateQueries({ queryKey: ['face-logs'] })
      await queryClient.invalidateQueries({ queryKey: ['unregistered-subjects'] })

      const msg = `Sighting transferred to ${transferTargetKey} successfully.`
      setMergeNotification(msg)
      setTimeout(() => setMergeNotification(null), 6000)

      // Also update activeSightingsPerson if open
      if (activeSightingsPerson) {
        const remainingLogs = activeSightingsPerson.allLogs.filter((l) => l.id !== transferSightingLog.id)
        if (remainingLogs.length === 0) {
          setActiveSightingsPerson(null)
        } else {
          setActiveSightingsPerson({
            ...activeSightingsPerson,
            totalSightings: remainingLogs.length,
            allLogs: remainingLogs,
          })
        }
      }

      setTransferSightingLog(null)
      setTransferTargetKey('')
    } catch (err) {
      console.error('Transfer failed:', err)
      alert(`Transfer failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setIsTransferring(false)
    }
  }

  // Compute persons involved in the current merge modal
  const modalPersons = useMemo(() => {
    if (mergeSourcePerson) {
      const target = uniquePersons.find((p) => p.key === mergeTargetKey)
      return {
        target: target || null,
        sources: [mergeSourcePerson],
        allOptions: uniquePersons.filter((p) => p.key !== mergeSourcePerson.key),
      }
    } else {
      const selected = uniquePersons.filter((p) => selectedPersonKeys.includes(p.key))
      const target = selected.find((p) => p.key === mergeTargetKey) || selected[0] || null
      const sources = selected.filter((p) => p.key !== target?.key)
      return {
        target,
        sources,
        allOptions: selected,
      }
    }
  }, [mergeSourcePerson, mergeTargetKey, selectedPersonKeys, uniquePersons])

  return (
    <div className="space-y-6">
      {/* Logical Segregation & Mode Header Banner */}
      <div className="relative overflow-hidden rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-card to-card p-5 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="flex size-7 items-center justify-center rounded-lg bg-amber-500/20 text-amber-500">
                <ScanFace className="size-4" />
              </span>
              <h2 className="text-lg font-bold tracking-tight">Footage Detected Persons & Faces</h2>
              <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-[11px] text-amber-500">
                Unique Identity Clustering
              </Badge>
              <Badge variant="outline" className="border-emerald-500/40 bg-emerald-500/10 text-[11px] text-emerald-400">
                <CheckCircle2 className="mr-1 size-3" />
                Zero Live DB Pollution
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Each unique individual detected across footage is automatically consolidated into a distinct identity (<code className="font-mono text-amber-400">Person 1..X</code>).
              Multiple frame sightings of the same human face are aggregated so every individual is shown uniquely.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Batch Selector */}
            <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 shadow-xs">
              <HardDrive className="size-3.5 text-muted-foreground" />
              <select
                id="cctv-batch-select"
                aria-label="CCTV Batch"
                value={selectedBatchId || ''}
                onChange={(e) => {
                  setSelectedBatchId(e.target.value || null)
                  setPage(0)
                  setSelectedPersonKeys([])
                }}
                className="bg-transparent text-xs font-medium focus:outline-none"
              >
                <option value="" className="bg-background">
                  All CCTV Batches ({batches.length})
                </option>
                {batches.map((b) => (
                  <option key={b.id} value={b.id} className="bg-background">
                    {b.name} ({b.cameraCount} cam, {b.totalDetections} faces)
                  </option>
                ))}
              </select>
            </div>

            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={() => setShowRosterModal(!showRosterModal)}
            >
              <Database className="size-3.5 text-cyan-400" />
              <span>{showRosterModal ? 'Hide Live Roster' : 'Compare Live Roster'}</span>
            </Button>
          </div>
        </div>
      </div>

      {/* Merge Success Alert Notification Banner */}
      {mergeNotification && (
        <div className="flex items-center justify-between rounded-xl border border-emerald-500/40 bg-emerald-500/15 p-4 text-emerald-300 shadow-md animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="size-5 text-emerald-400 shrink-0" />
            <span className="text-xs font-semibold">{mergeNotification}</span>
          </div>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setMergeNotification(null)}
            className="text-emerald-400 hover:text-emerald-200"
          >
            <X className="size-4" />
          </Button>
        </div>
      )}

      {/* KPI Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="p-4 bg-card/60 border-border">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Unique Persons</span>
            <Users className="size-4 text-primary" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-foreground">{stats.uniquePersonsCount}</p>
          <span className="text-[11px] text-muted-foreground">
            Consolidated from {stats.totalSightings} frame detections
          </span>
        </Card>

        <Card className="p-4 bg-card/60 border-border">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Recognized Staff / VIP</span>
            <UserCheck className="size-4 text-emerald-400" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-emerald-400">{stats.uniqueRecognized}</p>
          <span className="text-[11px] text-muted-foreground">
            Matched with live enrolled profiles
          </span>
        </Card>

        <Card className="p-4 bg-card/60 border-border">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Unregistered Subjects</span>
            <ScanFace className="size-4 text-amber-400" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-amber-400">{stats.uniqueUnregistered}</p>
          <span className="text-[11px] text-muted-foreground">
            Clustered as Person 1..{stats.uniqueUnregistered || 0}
          </span>
        </Card>

        <Card className="p-4 bg-card/60 border-border">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-medium">Security Alerts</span>
            <AlertTriangle className="size-4 text-destructive" />
          </div>
          <p className="mt-2 text-2xl font-bold tracking-tight text-destructive">{stats.flaggedCount}</p>
          <span className="text-[11px] text-muted-foreground">
            Watchlist / Blacklist footage hits
          </span>
        </Card>
      </div>

      {/* Roster Reference Comparison Panel (if toggled) */}
      {showRosterModal && (
        <Card className="border-cyan-500/30 bg-cyan-950/10 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <Database className="size-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-cyan-300">
                  Enrolled Live Reference Roster (Read-Only Gallery)
                </h3>
                <Badge variant="outline" className="border-cyan-500/40 text-[10px] text-cyan-400">
                  Read-Only Cross-Reference
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground">
                This is the live system directory ({enrolledProfiles.length} profiles). The offline CCTV recognition pipeline
                reads vectors from this database to identify employees seen in footage, but <strong>NEVER writes or modifies</strong> these records.
              </p>
            </div>
            <Button size="xs" variant="ghost" onClick={() => setShowRosterModal(false)}>
              Close
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
            {enrolledProfiles.slice(0, 16).map((p) => (
              <div
                key={p.id}
                className="flex flex-col items-center gap-1.5 rounded-lg border border-border bg-card/80 p-2.5 text-center text-xs shadow-xs"
              >
                <FaceTile tone="blue" size="md" />
                <span className="font-medium truncate max-w-full text-foreground">{p.name}</span>
                <span className="text-[10px] text-muted-foreground capitalize">{p.role}</span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Floating Selection Merge Action Bar (Appears when 1 or more persons checked) */}
      {viewMode === 'unique' && selectedPersonKeys.length > 0 && (
        <div className="flex items-center justify-between rounded-xl border border-violet-500/40 bg-gradient-to-r from-violet-950/40 via-card to-card p-3 shadow-lg animate-in fade-in slide-in-from-top-2">
          <div className="flex items-center gap-3">
            <div className="flex size-7 items-center justify-center rounded-lg bg-violet-500/20 text-violet-400">
              <GitMerge className="size-4" />
            </div>
            <div>
              <span className="text-xs font-bold text-foreground">
                {selectedPersonKeys.length} {selectedPersonKeys.length === 1 ? 'Person' : 'Persons'} Selected
              </span>
              <p className="text-[11px] text-muted-foreground">
                {selectedPersonKeys.length === 1
                  ? 'Select at least 1 more person to merge multiple recordings into a single identity.'
                  : `Selected: ${selectedPersonKeys.join(', ')}. Ready to merge into one person.`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setSelectedPersonKeys([])}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </Button>
            <Button
              size="sm"
              variant="default"
              disabled={selectedPersonKeys.length < 2}
              onClick={handleOpenMergeSelected}
              className="gap-1.5 text-xs font-bold bg-violet-600 hover:bg-violet-500 text-white shadow-xs"
            >
              <GitMerge className="size-3.5" />
              <span>Merge Selected ({selectedPersonKeys.length})</span>
            </Button>
          </div>
        </div>
      )}

      {/* Main Persons & Detections Table Card */}
      <Card className="gap-0 py-0 border-border">
        <CardHeader className="border-b border-border p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <SectionHeading
              icon={ScanFace}
              title={viewMode === 'unique' ? 'Unique Detected Persons' : 'All Sighting Detections Trail'}
              count={currentTotal}
              description={
                viewMode === 'unique'
                  ? 'Each unique human face detected in the footage appears exactly once with aggregated sightings'
                  : 'Chronological raw facial crops extracted frame-by-frame across video streams'
              }
            />

            {/* View Mode Toggle & Search */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Primary View Toggle: Unique Persons vs All Sightings */}
              <div className="flex items-center rounded-lg border border-border bg-muted/40 p-0.5">
                <Button
                  size="xs"
                  variant={viewMode === 'unique' ? 'secondary' : 'ghost'}
                  className={cn(
                    'h-7 px-2.5 text-xs font-semibold transition-all',
                    viewMode === 'unique' && 'bg-background shadow-xs text-foreground font-bold'
                  )}
                  onClick={() => {
                    setViewMode('unique')
                    setPage(0)
                  }}
                >
                  <Users className="mr-1.5 size-3.5 text-primary" />
                  <span>Unique Persons ({uniquePersons.length})</span>
                </Button>
                <Button
                  size="xs"
                  variant={viewMode === 'all' ? 'secondary' : 'ghost'}
                  className={cn(
                    'h-7 px-2.5 text-xs transition-all',
                    viewMode === 'all' && 'bg-background shadow-xs text-foreground font-bold'
                  )}
                  onClick={() => {
                    setViewMode('all')
                    setPage(0)
                  }}
                >
                  <Layers className="mr-1.5 size-3.5 text-amber-400" />
                  <span>All Sightings Trail ({rawLogs.length})</span>
                </Button>
              </div>

              {/* Search input */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value)
                    setPage(0)
                  }}
                  placeholder={viewMode === 'unique' ? 'Search Person 1, camera...' : 'Search subject / camera...'}
                  className="h-8 w-52 pl-8 text-xs"
                />
              </div>
            </div>
          </div>

          {/* Filter Pills & Quality Gates */}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-2.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                size="xs"
                variant={statusFilter === 'all' ? 'secondary' : 'ghost'}
                className={cn('text-xs', statusFilter === 'all' && 'ring-1 ring-inset ring-border font-bold')}
                onClick={() => {
                  setStatusFilter('all')
                  setPage(0)
                }}
              >
                {viewMode === 'unique' ? 'All Unique Persons' : 'All Detections'}
              </Button>
              <Button
                size="xs"
                variant={statusFilter === 'recognized' ? 'secondary' : 'ghost'}
                className={cn('text-xs', statusFilter === 'recognized' && 'ring-1 ring-inset ring-border text-emerald-400 font-bold')}
                onClick={() => {
                  setStatusFilter('recognized')
                  setPage(0)
                }}
              >
                <UserCheck className="mr-1 size-3 text-emerald-400" />
                Recognized Profiles
              </Button>
              <Button
                size="xs"
                variant={statusFilter === 'unknown' ? 'secondary' : 'ghost'}
                className={cn('text-xs', statusFilter === 'unknown' && 'ring-1 ring-inset ring-border text-amber-400 font-bold')}
                onClick={() => {
                  setStatusFilter('unknown')
                  setPage(0)
                }}
              >
                <ScanFace className="mr-1 size-3 text-amber-400" />
                Unregistered (Person 1..X)
              </Button>
              <Button
                size="xs"
                variant={statusFilter === 'flagged' ? 'secondary' : 'ghost'}
                className={cn('text-xs', statusFilter === 'flagged' && 'ring-1 ring-inset ring-border text-destructive font-bold')}
                onClick={() => {
                  setStatusFilter('flagged')
                  setPage(0)
                }}
              >
                <AlertTriangle className="mr-1 size-3 text-destructive" />
                Security Alerts
              </Button>
            </div>

            {/* Quality & Noise Gate Quick Toggles */}
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[11px] font-medium text-muted-foreground mr-1">Quality Gate:</span>
              <Button
                size="xs"
                variant={minConfidenceFilter >= 50 ? 'default' : 'outline'}
                className={cn(
                  'h-6 text-[11px] gap-1 px-2 transition-all',
                  minConfidenceFilter >= 50
                    ? 'bg-emerald-600 text-white font-bold hover:bg-emerald-500 border-emerald-500'
                    : 'text-muted-foreground hover:text-foreground'
                )}
                onClick={() => {
                  setMinConfidenceFilter(minConfidenceFilter >= 50 ? 0 : 50)
                  setPage(0)
                }}
              >
                <Sparkles className="size-3 text-emerald-300" />
                <span>High Conf (≥50%)</span>
              </Button>

              {viewMode === 'unique' && (
                <Button
                  size="xs"
                  variant={minSightingsFilter >= 2 ? 'default' : 'outline'}
                  className={cn(
                    'h-6 text-[11px] gap-1 px-2 transition-all',
                    minSightingsFilter >= 2
                      ? 'bg-cyan-600 text-white font-bold hover:bg-cyan-500 border-cyan-500'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  onClick={() => {
                    setMinSightingsFilter(minSightingsFilter >= 2 ? 1 : 2)
                    setPage(0)
                  }}
                >
                  <CheckCircle2 className="size-3 text-cyan-300" />
                  <span>Verified (≥2 Sightings)</span>
                </Button>
              )}

              {viewMode === 'unique' && (
                <Button
                  size="xs"
                  variant={showTransientNoise ? 'secondary' : 'ghost'}
                  className={cn(
                    'h-6 text-[11px] gap-1 px-2 transition-all',
                    showTransientNoise
                      ? 'border border-amber-500/40 text-amber-300 font-bold'
                      : 'text-muted-foreground hover:text-foreground'
                  )}
                  onClick={() => {
                    setShowTransientNoise(!showTransientNoise)
                    setPage(0)
                  }}
                >
                  <ScanFace className="size-3 text-amber-400" />
                  <span>{showTransientNoise ? 'Hide 1-Shot Noise' : 'Show 1-Shot Noise'}</span>
                </Button>
              )}

              {(minConfidenceFilter > 0 || minSightingsFilter > 1 || showTransientNoise) && (
                <Button
                  size="xs"
                  variant="ghost"
                  className="h-6 text-[10px] text-muted-foreground hover:text-foreground px-1.5"
                  onClick={() => {
                    setMinConfidenceFilter(0)
                    setMinSightingsFilter(1)
                    setShowTransientNoise(false)
                    setPage(0)
                  }}
                >
                  Reset
                </Button>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {isLoading ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Loading footage face extractions...
            </div>
          ) : currentTotal === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <ScanFace className="size-12 text-muted-foreground/30 mb-3" />
              <p className="text-sm font-semibold">No Persons Ingested in Current Selection</p>
              <p className="mt-1 max-w-md text-xs text-muted-foreground">
                {rawLogs.length === 0
                  ? 'Run "Ingest Face Recognition" on your footage folder in the CCTV Audit tab to extract and index faces.'
                  : 'No persons match your current search or status filter.'}
              </p>
            </div>
          ) : viewMode === 'unique' ? (
            /* ============================================================== */
            /* VIEW MODE: UNIQUE PERSONS (EACH FACE DISPLAYED EXACTLY ONCE)  */
            /* ============================================================== */
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="w-10 pl-4">
                    <input
                      type="checkbox"
                      aria-label="Select all persons on page"
                      checked={
                        uniqueRows.length > 0 &&
                        uniqueRows.every((p) => selectedPersonKeys.includes(p.key))
                      }
                      onChange={toggleSelectAllCurrentPage}
                      className="size-3.5 rounded border-border accent-violet-600 cursor-pointer"
                    />
                  </TableHead>
                  <TableHead>Face Crop</TableHead>
                  <TableHead>Unique Person Name</TableHead>
                  <TableHead>Footage Camera & Source Clip</TableHead>
                  <TableHead>Space-Time Span (IST)</TableHead>
                  <TableHead>Peak Confidence</TableHead>
                  <TableHead>Classification</TableHead>
                  <TableHead className="pr-4 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {uniqueRows.map((p) => {
                  const best = p.bestLog
                  const isChecked = selectedPersonKeys.includes(p.key)
                  return (
                    <TableRow
                      key={p.key}
                      className={cn(
                        'hover:bg-muted/30 transition-colors',
                        isChecked && 'bg-violet-950/20'
                      )}
                    >
                      {/* Checkbox */}
                      <TableCell className="w-10 pl-4">
                        <input
                          type="checkbox"
                          aria-label={`Select ${p.name}`}
                          checked={isChecked}
                          onChange={() => togglePersonSelection(p.key)}
                          className="size-3.5 rounded border-border accent-violet-600 cursor-pointer"
                        />
                      </TableCell>

                      {/* Face Thumbnail */}
                      <TableCell>
                        <div className="relative size-11 overflow-hidden rounded-md border border-border bg-black/40">
                          {best.faceImage ? (
                            <img
                              src={
                                best.faceImage.startsWith('data:')
                                  ? best.faceImage
                                  : `data:image/jpeg;base64,${best.faceImage}`
                              }
                              alt={p.name}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <FaceTile tone={best.snapshotTone} size="md" />
                          )}
                        </div>
                      </TableCell>

                      {/* Unique Person Name & Sightings count */}
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span
                              className="font-bold text-sm text-foreground hover:text-emerald-400 cursor-pointer transition-colors"
                              onClick={() => {
                                setRenameTargetPerson(p)
                                setCustomNameInput(p.name)
                              }}
                              title="Click to rename or assign to enrolled profile"
                            >
                              {p.name}
                            </span>
                            <button
                              type="button"
                              className="text-muted-foreground/60 hover:text-emerald-400 transition-colors p-0.5 rounded hover:bg-muted"
                              onClick={() => {
                                setRenameTargetPerson(p)
                                setCustomNameInput(p.name)
                              }}
                              title="Edit name or assign profile"
                            >
                              <Edit3 className="size-3" />
                            </button>
                            {p.role && <RoleBadge role={p.role} />}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <Badge
                              variant="secondary"
                              className="font-mono text-[10px] bg-primary/10 text-primary border-primary/20 cursor-pointer hover:bg-primary/20"
                              onClick={() => setActiveSightingsPerson(p)}
                              title="Click to view all sightings of this person"
                            >
                              <Eye className="mr-1 size-2.5" />
                              {p.totalSightings} {p.totalSightings === 1 ? 'sighting' : 'sightings'}
                            </Badge>
                          </div>
                        </div>
                      </TableCell>

                      {/* Camera & Source Video */}
                      <TableCell>
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 font-medium text-xs">
                            <HardDrive className="size-3 text-primary" />
                            <span className="font-semibold text-foreground">
                              {p.cameras.join(', ') || 'CCTV Cam'}
                            </span>
                          </div>
                          {p.sourceVideos.length > 0 && (
                            <div className="space-y-0.5 text-[10px] font-mono">
                              <span
                                className="flex items-center gap-1 text-foreground/80 truncate max-w-[220px]"
                                title={p.sourceVideos.join(', ')}
                              >
                                <Film className="size-3 text-amber-500 shrink-0" />
                                <span className="truncate">{p.sourceVideos[0]}</span>
                              </span>
                              {p.firstElapsedSec != null && (
                                <span className="text-muted-foreground/80 flex items-center gap-1 pl-4 text-[9px]">
                                  <Clock className="size-2.5" />
                                  <span>
                                    {Math.floor(p.firstElapsedSec / 60)}m {Math.round(p.firstElapsedSec % 60)}s
                                    {p.lastElapsedSec != null && p.lastElapsedSec !== p.firstElapsedSec
                                      ? ` – ${Math.floor(p.lastElapsedSec / 60)}m ${Math.round(p.lastElapsedSec % 60)}s`
                                      : ''}{' '}
                                    into clip
                                  </span>
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </TableCell>

                      {/* Space-Time Span */}
                      <TableCell>
                        <div className="font-mono text-xs tabular-nums text-foreground">
                          {formatTime(p.firstSeen)}
                          {p.lastSeen !== p.firstSeen && ` – ${formatTime(p.lastSeen)}`}{' '}
                          <span className="text-[10px] text-muted-foreground font-sans">IST</span>
                          <div className="text-[10px] text-muted-foreground/70">
                            {formatDateTime(p.firstSeen).split(',')[0]}
                          </div>
                        </div>
                      </TableCell>

                      {/* Confidence */}
                      <TableCell>
                        <div className="space-y-0.5">
                          <ConfidenceMeter value={p.maxConfidence} />
                          <p className="text-[10px] text-muted-foreground font-mono">
                            Avg: {p.avgConfidence}%
                          </p>
                        </div>
                      </TableCell>

                      {/* Status */}
                      <TableCell>
                        {p.status === 'recognized' ? (
                          <StatusBadge status="recognized" />
                        ) : p.status === 'flagged' ? (
                          <StatusBadge status="flagged" />
                        ) : (
                          <Badge
                            variant="outline"
                            className="border-amber-500/40 bg-amber-500/10 text-amber-400 font-medium text-[11px]"
                          >
                            Unregistered (Indexed)
                          </Badge>
                        )}
                      </TableCell>

                      {/* Actions */}
                      <TableCell className="pr-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Edit / Change Name Button */}
                          <Button
                            size="xs"
                            variant="outline"
                            className="h-7 gap-1 font-mono text-[11px] border-emerald-500/30 text-emerald-400 hover:border-emerald-500 hover:bg-emerald-500/10"
                            title="Change name or assign to enrolled profile (jenisha, selvi, pravin)"
                            onClick={() => {
                              setRenameTargetPerson(p)
                              setCustomNameInput(p.name)
                            }}
                          >
                            <Edit3 className="size-3" />
                            <span>Edit Name</span>
                          </Button>

                          {/* Merge Action Button */}
                          <Button
                            size="xs"
                            variant="outline"
                            className="h-7 gap-1 font-mono text-[11px] hover:border-violet-500/50 hover:text-violet-400"
                            title="Merge this person into another identity"
                            onClick={() => handleOpenMergeSingle(p)}
                          >
                            <GitMerge className="size-3 text-violet-400" />
                            <span>Merge</span>
                          </Button>

                          <Button
                            size="xs"
                            variant="outline"
                            className="h-7 gap-1 font-mono text-[11px] hover:border-amber-500/50 hover:text-amber-400"
                            title="View all frame sightings of this individual"
                            onClick={() => setActiveSightingsPerson(p)}
                          >
                            <Eye className="size-3 text-amber-400" />
                            <span>Sightings ({p.totalSightings})</span>
                          </Button>

                          {onNavigateToForensic && (
                            <Button
                              size="xs"
                              variant="outline"
                              className="h-7 gap-1 font-mono text-[11px] hover:border-info/50 hover:text-info"
                              title="Trace Space-Time Trajectory"
                              onClick={() => onNavigateToForensic(p.name)}
                            >
                              <Route className="size-3 text-info" />
                              <span>Trajectory</span>
                            </Button>
                          )}

                          <Button
                            size="xs"
                            variant="ghost"
                            className="h-7 gap-1 font-mono text-[11px]"
                            onClick={() => setSelectedEventId(best.id)}
                            title="View AI Lineage Graph"
                          >
                            <Workflow className="size-3 text-primary" />
                            <span>Lineage</span>
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          ) : (
            /* ============================================================== */
            /* VIEW MODE: ALL SIGHTINGS TRAIL (CHRONOLOGICAL DETECTIONS)      */
            /* ============================================================== */
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="pl-4">Face Crop</TableHead>
                  <TableHead>Identified Person</TableHead>
                  <TableHead>Footage Camera / Clip</TableHead>
                  <TableHead>Recorded Time (IST)</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="pr-4 text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rawRows.map((l) => (
                  <TableRow key={l.id} className="hover:bg-muted/30">
                    <TableCell className="pl-4">
                      <div className="relative size-11 overflow-hidden rounded-md border border-border bg-black/40">
                        {l.faceImage ? (
                          <img
                            src={
                              l.faceImage.startsWith('data:')
                                ? l.faceImage
                                : `data:image/jpeg;base64,${l.faceImage}`
                            }
                            alt="Face Thumbnail"
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <FaceTile tone={l.snapshotTone} size="md" />
                        )}
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">
                            {l.profileName || (l.profileId ? `Person ${l.profileId.slice(-4)}` : `Person ${l.id.slice(-4)}`)}
                          </span>
                          {l.role && <RoleBadge role={l.role} />}
                        </div>
                        <p className="font-mono text-[10px] text-muted-foreground/70">
                          {l.id.slice(0, 18)}...
                        </p>
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="space-y-1">
                        <div className="flex items-center gap-1.5 font-medium text-xs">
                          <HardDrive className="size-3 text-primary" />
                          <span className="font-semibold text-foreground">{l.cameraName || l.cameraId}</span>
                        </div>
                        {l.sourceVideo ? (
                          <div className="space-y-0.5 text-[10px] font-mono">
                            <span className="flex items-center gap-1 text-foreground/80 truncate max-w-[220px]" title={l.sourceVideo}>
                              <Film className="size-3 text-amber-500 shrink-0" />
                              <span className="truncate">{l.sourceVideo}</span>
                            </span>
                            {l.videoElapsedSec != null && (
                              <span className="text-muted-foreground/80 flex items-center gap-1 pl-4 text-[9px]">
                                <Clock className="size-2.5" />
                                <span>{Math.floor(l.videoElapsedSec / 60)}m {Math.round(l.videoElapsedSec % 60)}s into clip</span>
                              </span>
                            )}
                          </div>
                        ) : (
                          <p className="font-mono text-[10px] text-muted-foreground">{l.cameraId}</p>
                        )}
                      </div>
                    </TableCell>

                    <TableCell>
                      <div className="font-mono text-xs tabular-nums text-foreground">
                        {formatTime(l.timestamp)} <span className="text-[10px] text-muted-foreground font-sans">IST</span>
                        <div className="text-[10px] text-muted-foreground/70">
                          {formatDateTime(l.timestamp).split(',')[0]}
                        </div>
                      </div>
                    </TableCell>

                    <TableCell>
                      <ConfidenceMeter value={l.confidence} />
                    </TableCell>

                    <TableCell>
                      {l.status === 'recognized' ? (
                        <StatusBadge status="recognized" />
                      ) : l.status === 'flagged' ? (
                        <StatusBadge status="flagged" />
                      ) : (
                        <Badge
                          variant="outline"
                          className="border-amber-500/40 bg-amber-500/10 text-amber-400 font-medium text-[11px]"
                        >
                          Unregistered (Indexed)
                        </Badge>
                      )}
                    </TableCell>

                    <TableCell className="pr-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {onNavigateToForensic && (
                          <Button
                            size="xs"
                            variant="outline"
                            className="h-7 gap-1 font-mono text-[11px] hover:border-info/50 hover:text-info"
                            title="Trace Space-Time Trajectory"
                            onClick={() => onNavigateToForensic(l.profileName || undefined)}
                          >
                            <Route className="size-3 text-info" />
                            <span>Trajectory</span>
                          </Button>
                        )}
                        <Button
                          size="xs"
                          variant="ghost"
                          className="h-7 gap-1 font-mono text-[11px]"
                          onClick={() => setSelectedEventId(l.id)}
                          title="View AI Lineage Graph"
                        >
                          <Workflow className="size-3 text-primary" />
                          <span>Lineage</span>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Pagination */}
          {pageCount > 1 && (
            <div className="flex items-center justify-between border-t border-border px-4 py-3">
              <span className="text-xs text-muted-foreground">
                Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, currentTotal)} of{' '}
                {currentTotal} {viewMode === 'unique' ? 'unique persons' : 'detections'}
              </span>
              <div className="flex items-center gap-1">
                <Button
                  size="xs"
                  variant="outline"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="size-3.5" />
                </Button>
                <span className="px-2 text-xs font-mono">
                  {page + 1} / {pageCount}
                </span>
                <Button
                  size="xs"
                  variant="outline"
                  disabled={page >= pageCount - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight className="size-3.5" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ============================================================== */}
      {/* MERGE IDENTITIES MODAL                                         */}
      {/* ============================================================== */}
      {mergeModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-xs animate-in fade-in">
          <Card className="max-h-[90vh] w-full max-w-xl overflow-hidden border-border bg-card shadow-2xl flex flex-col">
            <CardHeader className="border-b border-border p-4 bg-muted/20">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-violet-500/20 text-violet-400">
                    <GitMerge className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      Merge Duplicate Human Identities
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Combine recordings of the same individual across camera footage into one unified identity.
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="size-8 p-0"
                  disabled={isMerging}
                  onClick={() => {
                    setMergeModalOpen(false)
                    setMergeSourcePerson(null)
                  }}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </CardHeader>

            <CardContent className="overflow-y-auto p-5 space-y-4">
              {/* Select Target Identity */}
              <div className="space-y-2">
                <label className="text-xs font-bold text-foreground uppercase tracking-wider">
                  1. Select Primary Target Identity (Keep as Master):
                </label>
                <p className="text-xs text-muted-foreground">
                  All detections, camera appearances, and timestamps will be transferred under this identity.
                </p>

                <div className="grid grid-cols-1 gap-2 pt-1">
                  {modalPersons.allOptions.map((opt) => {
                    const isSelectedTarget = opt.key === mergeTargetKey
                    return (
                      <div
                        key={opt.key}
                        onClick={() => !isMerging && setMergeTargetKey(opt.key)}
                        className={cn(
                          'flex items-center justify-between rounded-lg border p-3 cursor-pointer transition-all',
                          isSelectedTarget
                            ? 'border-violet-500 bg-violet-950/20 ring-1 ring-violet-500'
                            : 'border-border bg-card/60 hover:border-border/80'
                        )}
                      >
                        <div className="flex items-center gap-3">
                          <div className="relative size-10 overflow-hidden rounded-md border border-border bg-black/40">
                            {opt.bestLog.faceImage ? (
                              <img
                                src={
                                  opt.bestLog.faceImage.startsWith('data:')
                                    ? opt.bestLog.faceImage
                                    : `data:image/jpeg;base64,${opt.bestLog.faceImage}`
                                }
                                alt={opt.name}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <FaceTile tone={opt.bestLog.snapshotTone} size="md" />
                            )}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-sm text-foreground">{opt.name}</span>
                              <Badge variant="outline" className="text-[10px] font-mono border-border">
                                {opt.totalSightings} sightings
                              </Badge>
                            </div>
                            <p className="text-[11px] text-muted-foreground">
                              {opt.cameras.join(', ')} • {opt.sourceVideos[0] || 'Clip'}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-2">
                          {isSelectedTarget ? (
                            <Badge className="bg-violet-600 text-white text-[11px] font-bold">
                              <Check className="mr-1 size-3" />
                              Target Identity
                            </Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground font-mono">Select</span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Source Persons to be merged */}
              <div className="space-y-2 pt-2 border-t border-border">
                <label className="text-xs font-bold text-foreground uppercase tracking-wider">
                  2. Identities to be merged and consolidated:
                </label>
                <div className="space-y-2">
                  {modalPersons.sources.map((src) => (
                    <div
                      key={src.key}
                      className="flex items-center justify-between rounded-lg border border-amber-500/30 bg-amber-950/10 p-2.5"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className="relative size-8 overflow-hidden rounded border border-amber-500/40 bg-black/40">
                          {src.bestLog.faceImage ? (
                            <img
                              src={
                                src.bestLog.faceImage.startsWith('data:')
                                  ? src.bestLog.faceImage
                                  : `data:image/jpeg;base64,${src.bestLog.faceImage}`
                              }
                              alt={src.name}
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <FaceTile tone={src.bestLog.snapshotTone} size="sm" />
                          )}
                        </div>
                        <div>
                          <span className="font-semibold text-xs text-amber-300">{src.name}</span>
                          <span className="text-[11px] text-muted-foreground ml-2">
                            ({src.totalSightings} sightings)
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 text-[11px] font-mono text-amber-400">
                        <span>Merge into</span>
                        <ArrowRight className="size-3" />
                        <span className="font-bold">{modalPersons.target?.name || 'Target'}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Impact Summary Callout */}
              <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs space-y-1">
                <div className="flex items-center gap-1.5 font-bold text-foreground">
                  <Sparkles className="size-3.5 text-primary" />
                  <span>Consolidation Impact:</span>
                </div>
                <p className="text-muted-foreground text-[11px] leading-relaxed">
                  After merging,{' '}
                  <strong className="text-foreground">{modalPersons.target?.name || 'Target'}</strong> will have{' '}
                  <strong className="text-primary font-mono">
                    {(modalPersons.target?.totalSightings || 0) +
                      modalPersons.sources.reduce((acc, s) => acc + s.totalSightings, 0)}{' '}
                    total sightings
                  </strong>{' '}
                  across all footage clips. The duplicate source identity will be archived and removed from the active persons list.
                </p>
              </div>
            </CardContent>

            <div className="flex items-center justify-end gap-2 border-t border-border p-3.5 bg-muted/20">
              <Button
                size="sm"
                variant="outline"
                disabled={isMerging}
                onClick={() => {
                  setMergeModalOpen(false)
                  setMergeSourcePerson(null)
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="default"
                disabled={isMerging || !modalPersons.target || modalPersons.sources.length === 0}
                onClick={handleExecuteMerge}
                className="gap-2 font-bold bg-violet-600 hover:bg-violet-500 text-white"
              >
                {isMerging ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Merging Records...</span>
                  </>
                ) : (
                  <>
                    <GitMerge className="size-3.5" />
                    <span>Confirm & Merge Records</span>
                  </>
                )}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Individual Person Sightings Modal */}
      {activeSightingsPerson && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <Card className="max-h-[90vh] w-full max-w-3xl overflow-hidden border-border bg-card shadow-2xl flex flex-col">
            <CardHeader className="border-b border-border p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="relative size-12 overflow-hidden rounded-md border border-amber-500/40 bg-black/40">
                    {activeSightingsPerson.bestLog.faceImage ? (
                      <img
                        src={
                          activeSightingsPerson.bestLog.faceImage.startsWith('data:')
                            ? activeSightingsPerson.bestLog.faceImage
                            : `data:image/jpeg;base64,${activeSightingsPerson.bestLog.faceImage}`
                        }
                        alt={activeSightingsPerson.name}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <FaceTile tone={activeSightingsPerson.bestLog.snapshotTone} size="lg" />
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-base font-bold text-foreground">
                        {activeSightingsPerson.name}
                      </h3>
                      <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-400 text-xs font-mono">
                        {activeSightingsPerson.totalSightings} Sightings
                      </Badge>
                      <Button
                        size="xs"
                        variant="outline"
                        className="h-6 gap-1 border-emerald-500/30 text-emerald-400 text-[10px] hover:border-emerald-500 hover:bg-emerald-500/10"
                        onClick={() => {
                          setRenameTargetPerson(activeSightingsPerson)
                          setCustomNameInput(activeSightingsPerson.name)
                        }}
                      >
                        <Edit3 className="size-2.5" />
                        <span>Change Name</span>
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Extracted from {activeSightingsPerson.sourceVideos.join(', ') || 'Footage'} • First seen {formatTime(activeSightingsPerson.firstSeen)} IST
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="size-8 p-0"
                  onClick={() => setActiveSightingsPerson(null)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </CardHeader>

            <CardContent className="overflow-y-auto p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground font-medium">
                  Chronological Face Crops for {activeSightingsPerson.name}:
                </p>
                <span className="text-[10px] text-muted-foreground">
                  Use &quot;Move&quot; to detach any mismatched sighting to another identity
                </span>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                {activeSightingsPerson.allLogs.map((log, idx) => (
                  <div
                    key={log.id}
                    className="flex flex-col rounded-lg border border-border bg-card/60 p-2 text-xs space-y-1.5 hover:border-primary/40 transition-all"
                  >
                    <div className="relative aspect-square w-full overflow-hidden rounded border border-border bg-black/30">
                      {log.faceImage ? (
                        <img
                          src={
                            log.faceImage.startsWith('data:')
                              ? log.faceImage
                              : `data:image/jpeg;base64,${log.faceImage}`
                          }
                          alt={`Sighting ${idx + 1}`}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <FaceTile tone={log.snapshotTone} size="lg" />
                      )}
                      <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 font-mono text-[9px] text-white">
                        #{idx + 1}
                      </span>
                    </div>

                    <div className="space-y-0.5 font-mono text-[10px]">
                      <div className="flex items-center justify-between text-muted-foreground">
                        <span>Time:</span>
                        <span className="text-foreground">{formatTime(log.timestamp)}</span>
                      </div>
                      {log.videoElapsedSec != null && (
                        <div className="flex items-center justify-between text-muted-foreground">
                          <span>Offset:</span>
                          <span className="text-amber-400">
                            {Math.floor(log.videoElapsedSec / 60)}m {Math.round(log.videoElapsedSec % 60)}s
                          </span>
                        </div>
                      )}
                      <div className="flex items-center justify-between text-muted-foreground">
                        <span>Confidence:</span>
                        <span className="text-emerald-400 font-bold">{Math.round(log.confidence)}%</span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 pt-0.5">
                      <Button
                        size="xs"
                        variant="ghost"
                        className="h-6 flex-1 text-[10px] gap-1 font-mono text-muted-foreground hover:text-foreground"
                        onClick={() => {
                          setSelectedEventId(log.id)
                        }}
                      >
                        <Workflow className="size-2.5 text-primary" />
                        Lineage
                      </Button>
                      <Button
                        size="xs"
                        variant="ghost"
                        className="h-6 flex-1 text-[10px] gap-1 font-mono text-amber-400 hover:text-amber-300 hover:bg-amber-500/10"
                        title="Move this sighting to another person"
                        onClick={() => {
                          setTransferSightingLog(log)
                          const otherPerson = uniquePersons.find((up) => up.key !== activeSightingsPerson.key)
                          setTransferTargetKey(otherPerson?.key || '')
                        }}
                      >
                        <ArrowRight className="size-2.5" />
                        Move
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>

            <div className="flex items-center justify-between border-t border-border p-3 bg-muted/20">
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs font-mono border-emerald-500/30 text-emerald-400 hover:border-emerald-500 hover:bg-emerald-500/10"
                  onClick={() => {
                    const p = activeSightingsPerson
                    setRenameTargetPerson(p)
                    setCustomNameInput(p.name)
                  }}
                >
                  <Edit3 className="size-3.5" />
                  <span>Change Name / Assign</span>
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs font-mono hover:border-violet-500/50 hover:text-violet-400"
                  onClick={() => {
                    const p = activeSightingsPerson
                    setActiveSightingsPerson(null)
                    handleOpenMergeSingle(p)
                  }}
                >
                  <GitMerge className="size-3.5 text-violet-400" />
                  <span>Merge this Person...</span>
                </Button>
                {onNavigateToForensic && (
                  <Button
                    size="sm"
                    variant="outline"
                    className="gap-1.5 text-xs font-mono"
                    onClick={() => {
                      onNavigateToForensic(activeSightingsPerson.name)
                      setActiveSightingsPerson(null)
                    }}
                  >
                    <Route className="size-3.5 text-info" />
                    <span>Trace Full Trajectory</span>
                  </Button>
                )}
              </div>
              <Button
                size="sm"
                variant="secondary"
                className="text-xs"
                onClick={() => setActiveSightingsPerson(null)}
              >
                Close
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Rename & Assign Identity Modal */}
      {renameTargetPerson && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <Card className="max-h-[90vh] w-full max-w-xl overflow-hidden border-border bg-card shadow-2xl flex flex-col">
            <CardHeader className="border-b border-border p-4 bg-muted/20">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
                    <UserCheck className="size-4" />
                  </div>
                  <div>
                    <h3 className="text-base font-bold text-foreground">
                      Change Name & Assign Identity
                    </h3>
                    <p className="text-xs text-muted-foreground">
                      Updating <strong className="text-foreground">{renameTargetPerson.name}</strong> ({renameTargetPerson.totalSightings} footage sightings)
                    </p>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="size-8 p-0"
                  onClick={() => setRenameTargetPerson(null)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </CardHeader>

            <CardContent className="overflow-y-auto p-5 space-y-5">
              {/* Target Face Preview */}
              <div className="flex items-center gap-3.5 rounded-lg border border-border bg-muted/30 p-3">
                <div className="relative size-14 overflow-hidden rounded-md border border-amber-500/40 bg-black/40 shrink-0">
                  {renameTargetPerson.bestLog.faceImage ? (
                    <img
                      src={
                        renameTargetPerson.bestLog.faceImage.startsWith('data:')
                          ? renameTargetPerson.bestLog.faceImage
                          : `data:image/jpeg;base64,${renameTargetPerson.bestLog.faceImage}`
                      }
                      alt={renameTargetPerson.name}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <FaceTile tone={renameTargetPerson.bestLog.snapshotTone} size="lg" />
                  )}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-foreground">{renameTargetPerson.name}</span>
                    <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-[10px] text-amber-400 font-mono">
                      {renameTargetPerson.totalSightings} Sightings
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    First seen {formatTime(renameTargetPerson.firstSeen)} IST • Peak Confidence: {Math.round(renameTargetPerson.maxConfidence)}%
                  </p>
                </div>
              </div>

              {/* Option 1: 1-Click Assign to Enrolled Profiles */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-semibold text-xs text-foreground">
                    <Sparkles className="size-3.5 text-emerald-400" />
                    <span>Assign to Saved Enrolled Profile:</span>
                  </div>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    1-Click recognition & biometric link
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                  {knownProfiles.map((p) => {
                    const isVip = p.role === 'vip'
                    const isEmployee = p.role === 'employee'
                    const isMatchedTarget = renameTargetPerson.name.toLowerCase() === p.name.toLowerCase()
                    return (
                      <button
                        key={p.id}
                        type="button"
                        disabled={isRenaming}
                        onClick={() => handleAssignToProfile(p.id, p.name)}
                        className={cn(
                          "flex flex-col items-start p-3 rounded-lg border text-left transition-all hover:scale-[1.02] cursor-pointer",
                          isMatchedTarget
                            ? "border-emerald-500 bg-emerald-500/15 ring-1 ring-emerald-500"
                            : isVip
                            ? "border-amber-500/40 bg-amber-500/5 hover:border-amber-500 hover:bg-amber-500/15"
                            : isEmployee
                            ? "border-blue-500/40 bg-blue-500/5 hover:border-blue-500 hover:bg-blue-500/15"
                            : "border-border bg-card/60 hover:border-primary/50 hover:bg-muted/40"
                        )}
                      >
                        <div className="flex items-center justify-between w-full mb-1">
                          <span className="font-bold text-sm capitalize text-foreground">
                            {p.name}
                          </span>
                          <RoleBadge role={p.role} />
                        </div>
                        <span className="text-[11px] text-muted-foreground">
                          {p.embeddingCount || 0} enrolled vectors
                        </span>
                        <div className="mt-2.5 flex items-center gap-1 text-[10px] font-mono text-emerald-400 font-semibold">
                          <Check className="size-3" />
                          <span>Assign as {p.name}</span>
                        </div>
                      </button>
                    )
                  })}
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  Assigning automatically converts all {renameTargetPerson.totalSightings} footage detections to <strong className="text-emerald-400">Recognized</strong>, attaches their CCTV facial embedding to the profile, and increments the Recognized Staff / VIP counter.
                </p>
              </div>

              {/* Divider */}
              <div className="relative flex items-center justify-center">
                <div className="border-t border-border w-full" />
                <span className="bg-card px-3 text-[11px] font-mono text-muted-foreground uppercase">
                  or custom name
                </span>
              </div>

              {/* Option 2: Custom Rename */}
              <div className="space-y-2.5">
                <label className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Edit3 className="size-3.5 text-primary" />
                  <span>Custom Display Name:</span>
                </label>
                <div className="flex gap-2">
                  <Input
                    value={customNameInput}
                    onChange={(e) => setCustomNameInput(e.target.value)}
                    placeholder="e.g. Pravin Desk, Selvi Counter, Visitor A..."
                    className="h-9 text-xs"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCustomRename()
                    }}
                  />
                  <Button
                    size="sm"
                    disabled={isRenaming || !customNameInput.trim() || customNameInput.trim() === renameTargetPerson.name}
                    onClick={handleCustomRename}
                    className="h-9 font-semibold text-xs gap-1.5 bg-primary text-primary-foreground shrink-0"
                  >
                    {isRenaming ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
                    <span>Save Name</span>
                  </Button>
                </div>
              </div>
            </CardContent>

            <div className="flex items-center justify-end border-t border-border p-3 bg-muted/20">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setRenameTargetPerson(null)}
                className="text-xs"
              >
                Cancel
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* Move / Transfer Sighting Modal */}
      {transferSightingLog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-xs">
          <Card className="max-h-[90vh] w-full max-w-md overflow-hidden border-border bg-card shadow-2xl flex flex-col">
            <CardHeader className="border-b border-border p-4 bg-muted/20">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <ArrowRight className="size-4 text-amber-400" />
                  <h3 className="text-base font-bold text-foreground">
                    Move Sighting to Another Person
                  </h3>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="size-8 p-0"
                  onClick={() => setTransferSightingLog(null)}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </CardHeader>

            <CardContent className="p-4 space-y-4">
              {/* Sighting Preview */}
              <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 p-2.5">
                <div className="relative size-14 overflow-hidden rounded border border-border bg-black/40 shrink-0">
                  {transferSightingLog.faceImage ? (
                    <img
                      src={
                        transferSightingLog.faceImage.startsWith('data:')
                          ? transferSightingLog.faceImage
                          : `data:image/jpeg;base64,${transferSightingLog.faceImage}`
                      }
                      alt="Sighting to transfer"
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <FaceTile tone={transferSightingLog.snapshotTone} size="lg" />
                  )}
                </div>
                <div className="space-y-0.5 text-xs font-mono">
                  <div className="text-muted-foreground">
                    Captured at: <span className="text-foreground font-semibold">{formatTime(transferSightingLog.timestamp)} IST</span>
                  </div>
                  {transferSightingLog.videoElapsedSec != null && (
                    <div className="text-muted-foreground">
                      Offset: <span className="text-amber-400">{Math.floor(transferSightingLog.videoElapsedSec / 60)}m {Math.round(transferSightingLog.videoElapsedSec % 60)}s</span>
                    </div>
                  )}
                  <div className="text-muted-foreground">
                    Confidence: <span className="text-emerald-400">{Math.round(transferSightingLog.confidence)}%</span>
                  </div>
                </div>
              </div>

              {/* Target Person Selector */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-foreground">
                  Move this specific face crop to:
                </label>
                <select
                  aria-label="Target person or profile"
                  value={transferTargetKey}
                  onChange={(e) => setTransferTargetKey(e.target.value)}
                  className="w-full rounded-md border border-border bg-card p-2 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-primary"
                >
                  <option value="" disabled>Select target person or profile...</option>
                  <optgroup label="Footage Detected Persons">
                    {uniquePersons.map((p) => (
                      <option key={p.key} value={p.key}>
                        {p.name} ({p.totalSightings} sightings)
                      </option>
                    ))}
                  </optgroup>
                  <optgroup label="Saved Enrolled Profiles">
                    {knownProfiles.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.role})
                      </option>
                    ))}
                  </optgroup>
                </select>
              </div>

              <p className="text-[11px] text-muted-foreground">
                This frame detection will be immediately detached from the current person and reassigned to the selected identity.
              </p>
            </CardContent>

            <div className="flex items-center justify-end gap-2 border-t border-border p-3 bg-muted/20">
              <Button
                size="sm"
                variant="outline"
                disabled={isTransferring}
                onClick={() => setTransferSightingLog(null)}
                className="text-xs"
              >
                Cancel
              </Button>
              <Button
                size="sm"
                variant="default"
                disabled={isTransferring || !transferTargetKey}
                onClick={handleExecuteTransferSighting}
                className="gap-1.5 text-xs font-bold bg-amber-600 hover:bg-amber-500 text-white"
              >
                {isTransferring ? (
                  <>
                    <Loader2 className="size-3.5 animate-spin" />
                    <span>Moving Sighting...</span>
                  </>
                ) : (
                  <>
                    <ArrowRight className="size-3.5" />
                    <span>Confirm Move</span>
                  </>
                )}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {/* AI Provenance Drawer */}
      <LineageDrawer
        eventId={selectedEventId}
        onClose={() => setSelectedEventId(null)}
      />
    </div>
  )
}
