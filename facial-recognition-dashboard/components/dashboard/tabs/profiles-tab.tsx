'use client'

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assignUnregisteredSubject, deleteProfile, deleteProfileEmbeddings, deleteUnregisteredEvent, deleteUnregisteredSubject, fetchDuplicates, fetchProfiles, fetchUnregisteredSubjects, mergeUnregisteredSubjects, registerUnregisteredSubject, renameUnregisteredSubject, updateProfile } from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  FaceTile,
  RoleBadge,
  SectionHeading,
} from '@/components/dashboard/shared'
import { formatTime } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { EmbeddingStatus, Profile, ProfileRole, UnregisteredSubject } from '@/lib/types'
import {
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Copy,
  Check,
  Pencil,
  Trash2,
  GitMerge,
  ImagePlus,
  ScanFace,
  TriangleAlert,
  UserRoundPlus,
  UsersRound,
  X,
} from 'lucide-react'

const embeddingMeta: Record<
  EmbeddingStatus,
  { label: string; className: string; icon: React.ComponentType<{ className?: string }> }
> = {
  indexed: {
    label: 'Indexed',
    className: 'text-success',
    icon: CircleCheck,
  },
  pending: {
    label: 'Pending',
    className: 'text-warning',
    icon: CircleDashed,
  },
  stale: {
    label: 'Stale',
    className: 'text-warning',
    icon: TriangleAlert,
  },
  missing: {
    label: 'No embedding',
    className: 'text-destructive',
    icon: CircleSlash,
  },
}

const ROLE_FILTERS: Array<'all' | ProfileRole> = [
  'all',
  'employee',
  'vip',
  'visitor',
  'watchlist',
  'blacklist',
]

function ProfileCard({ profile, onSave, onClearVectors, onDelete }: { profile: Profile; onSave: (changes: { name: string; role: ProfileRole; department: string }) => void; onClearVectors: () => void; onDelete: () => void }) {
  const meta = embeddingMeta[profile.embeddingStatus]
  const Icon = meta.icon
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(profile.name)
  const [department, setDepartment] = useState(profile.department)
  const [draftRole, setDraftRole] = useState<ProfileRole>(profile.role)

  const startEditing = () => {
    setName(profile.name)
    setDepartment(profile.department)
    setDraftRole(profile.role)
    setEditing(true)
  }

  const cancelEditing = () => setEditing(false)

  const confirmEditing = () => {
    if (!name.trim()) return
    onSave({ name: name.trim(), role: draftRole, department: department.trim() })
    setEditing(false)
  }

  return (
    <Card
      className={cn(
        'gap-0 py-0',
        profile.role === 'blacklist' && 'ring-1 ring-inset ring-destructive/30',
      )}
    >
      <CardContent className="flex flex-col items-center gap-3 p-4 text-center">
        <FaceTile
          tone={profile.avatarTone}
          size="lg"
          flagged={profile.role === 'blacklist'}
        />
        <div className="w-full">
          {editing ? (
            <Input aria-label={`Name for ${profile.name}`} value={name} onChange={(event) => setName(event.target.value)} className="h-8 text-xs" />
          ) : <p className="text-sm font-semibold">{profile.name}</p>}
          <p className="font-mono text-[11px] text-muted-foreground">{profile.id}</p>
        </div>
        {editing ? (
          <div className="w-full space-y-2">
            <select aria-label={`Role for ${profile.name}`} value={draftRole} onChange={(event) => setDraftRole(event.target.value as ProfileRole)} className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs capitalize">
              {ROLE_FILTERS.slice(1).map((option) => <option key={option} value={option}>{option}</option>)}
            </select>
            <Input aria-label={`Department for ${profile.name}`} value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="Department" className="h-8 text-xs" />
            <div className="flex gap-2">
              <Button size="xs" className="flex-1" onClick={confirmEditing} disabled={!name.trim()}><Check /> Confirm</Button>
              <Button size="xs" variant="outline" onClick={cancelEditing}><X /></Button>
            </div>
            <Button size="xs" variant="ghost" className="w-full text-muted-foreground" disabled={profile.embeddingCount === 0} onClick={onClearVectors}>
              Clear {profile.embeddingCount} vectors
            </Button>
          </div>
        ) : (
          <div className="flex w-full items-center justify-between gap-2">
            <RoleBadge role={profile.role} />
            <div className="flex items-center gap-1.5">
              <Button size="xs" variant="outline" onClick={startEditing}><Pencil /> Edit</Button>
              <Button
                size="icon"
                variant="ghost"
                title={`Delete ${profile.name}`}
                aria-label={`Delete ${profile.name}`}
                className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                onClick={onDelete}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          </div>
        )}
        <div className="w-full space-y-1.5 border-t border-border pt-3 text-left">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Department</span>
            <span>{profile.department}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Embeddings</span>
            <span className="font-mono">{profile.embeddingCount}</span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Last seen</span>
            <span className="font-mono">
              {profile.lastSeen ? `${formatTime(profile.lastSeen)} IST` : '—'}
            </span>
          </div>
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Vector status</span>
            <span className={cn('flex items-center gap-1 font-medium', meta.className)}>
              <Icon className="size-3.5" />
              {meta.label}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function EnrolmentModal() {
  const [role, setRole] = useState<ProfileRole>('employee')
  const [open, setOpen] = useState(false)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm">
            <UserRoundPlus /> Enrol Individual
          </Button>
        }
      />
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Enrol New Individual</DialogTitle>
          <DialogDescription>
            Upload a reference image — the embedding is generated automatically and
            written to the pgvector index.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex items-center justify-center rounded-lg border-2 border-dashed border-border bg-card/40 p-6">
            <div className="flex flex-col items-center gap-2 text-center">
              <span className="flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <ImagePlus className="size-5" />
              </span>
              <p className="text-xs text-muted-foreground">
                Drop reference face or click to upload
              </p>
              <Button size="xs" variant="outline">
                Select image
              </Button>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">Full name</Label>
              <Input placeholder="e.g. Jane Doe" className="h-8 text-xs" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Department</Label>
              <Input placeholder="e.g. Engineering" className="h-8 text-xs" />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Role</Label>
            <div className="flex flex-wrap gap-1.5">
              {(['employee', 'vip', 'visitor', 'watchlist', 'blacklist'] as const).map(
                (r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setRole(r)}
                    className={cn(
                      'rounded-md border px-2.5 py-1 text-xs capitalize transition-colors',
                      role === r
                        ? 'border-info/40 bg-info/15 text-info'
                        : 'border-border bg-card/50 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {r}
                  </button>
                ),
              )}
            </div>
          </div>
          <div className="rounded-md bg-muted/50 p-2.5 text-xs text-muted-foreground">
            Auto-embedding: 512-d vector · model{' '}
            <span className="font-mono text-foreground">arcface-r100</span>
          </div>
        </div>
        <DialogFooter showCloseButton>
          <Button onClick={() => setOpen(false)}>
            <UserRoundPlus /> Generate embedding & enrol
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DedupPanel() {
  const { data: dupes = [] } = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => fetchDuplicates(),
  })
  const [merged, setMerged] = useState<string[]>([])

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Copy}
          title="Deduplication Utility"
          count={dupes.filter((d) => !merged.includes(d.id)).length}
          description="Potential duplicate identities by cosine similarity"
        />
      </CardHeader>
      <CardContent className="flex flex-col gap-2.5 p-3">
        {dupes.map((d) => {
          const isMerged = merged.includes(d.id)
          return (
            <div
              key={d.id}
              className={cn(
                'rounded-lg border border-border bg-card/50 p-3',
                isMerged && 'opacity-55',
              )}
            >
              <div className="flex items-center gap-3">
                <div className="flex items-center">
                  <FaceTile tone={d.profileA.avatarTone} size="md" />
                  <FaceTile tone={d.profileB.avatarTone} size="md" className="-ml-3 ring-2 ring-background" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm">
                    <span className="font-medium">{d.profileA.name}</span>
                    <span className="text-muted-foreground"> ≈ </span>
                    <span className="font-medium">{d.profileB.name}</span>
                  </p>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {d.sharedSightings} shared sightings
                  </p>
                </div>
                <Badge className="rounded-md bg-warning/15 font-mono text-warning">
                  {(d.cosineSimilarity * 100).toFixed(1)}%
                </Badge>
              </div>
              <Button
                size="xs"
                variant={isMerged ? 'ghost' : 'outline'}
                className="mt-2.5 w-full"
                disabled={isMerged}
                onClick={() => setMerged((prev) => [...prev, d.id])}
              >
                <GitMerge /> {isMerged ? 'Profiles merged' : 'Merge Profiles'}
              </Button>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}

function UnregisteredVectorsPanel({ profiles }: { profiles: Profile[] }) {
  const queryClient = useQueryClient()
  const { data: subjects = [], isLoading } = useQuery({
    queryKey: ['unregistered-vectors'],
    queryFn: fetchUnregisteredSubjects,
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['unregistered-vectors'] })
  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameUnregisteredSubject(id, name),
    onSuccess: refresh,
    onError: (err: any) => alert(`Failed to rename subject: ${err?.message || 'Unknown error'}`),
  })
  const registerMutation = useMutation({
    mutationFn: ({ id, name, role, department }: { id: string; name: string; role: ProfileRole; department?: string }) =>
      registerUnregisteredSubject(id, { name, role, department }),
    onSuccess: () => {
      refresh()
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setSelectedSubject(null)
    },
    onError: (err: any) => alert(`Failed to register profile: ${err?.message || 'Unknown error'}`),
  })
  const assignMutation = useMutation({
    mutationFn: ({ id, profileId }: { id: string; profileId: string }) => assignUnregisteredSubject(id, profileId),
    onSuccess: () => {
      refresh()
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setSelectedSubject(null)
    },
    onError: (err: any) => alert(`Failed to assign to profile: ${err?.message || 'Unknown error'}`),
  })
  const mergeMutation = useMutation({
    mutationFn: ({ id, sourceId }: { id: string; sourceId: string }) => mergeUnregisteredSubjects(id, sourceId),
    onSuccess: refresh,
    onError: (err: any) => alert(`Failed to merge subjects: ${err?.message || 'Unknown error'}`),
  })
  const deleteEventMutation = useMutation({
    mutationFn: ({ subjectId, eventId }: { subjectId: string; eventId: string }) => deleteUnregisteredEvent(subjectId, eventId),
    onSuccess: refresh,
    onError: (err: any) => alert(`Failed to delete event: ${err?.message || 'Unknown error'}`),
  })
  const deleteSubjectMutation = useMutation({
    mutationFn: deleteUnregisteredSubject,
    onSuccess: refresh,
    onError: (err: any) => alert(`Failed to delete subject: ${err?.message || 'Unknown error'}`),
  })

  const [selectedSubject, setSelectedSubject] = useState<UnregisteredSubject | null>(null)
  const [modalMode, setModalMode] = useState<'register' | 'assign'>('register')
  const [regName, setRegName] = useState('')
  const [regRole, setRegRole] = useState<ProfileRole>('visitor')
  const [regDept, setRegDept] = useState('')
  const [assignProfileId, setAssignProfileId] = useState('')

  const openActionModal = (subject: UnregisteredSubject, mode: 'register' | 'assign' = 'register') => {
    setSelectedSubject(subject)
    setModalMode(mode)
    setRegName(subject.displayName.startsWith('Unknown') ? '' : subject.displayName)
    setRegRole('visitor')
    setRegDept('')
    setAssignProfileId(profiles[0]?.id || '')
  }

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={ScanFace}
          title="Unregistered Vectors"
          count={subjects.length}
          description="Visual face captures awaiting identity registration or profile assignment"
        />
      </CardHeader>
      <CardContent className="p-4">
        {isLoading ? (
          <p className="py-8 text-center text-sm text-muted-foreground">Loading captures...</p>
        ) : subjects.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-12 text-center text-muted-foreground">
            <ScanFace className="size-8 opacity-50" />
            <p className="text-sm">No embedded unknown subjects found</p>
          </div>
        ) : (
          <div className="space-y-3">
            {subjects.map((subject) => (
              <div key={subject.id} className="rounded-lg border border-border bg-card/50 p-3 hover:border-border/80 transition-colors">
                <div className="flex items-start gap-3">
                  <div
                    className="cursor-pointer group relative"
                    title="Click to view & register"
                    onClick={() => openActionModal(subject, 'register')}
                  >
                    <FaceTile
                      image={subject.thumbnail}
                      tone="rose"
                      size="lg"
                      flagged
                      className="size-20 shadow-sm transition-transform duration-200 group-hover:scale-105"
                    />
                    <span className="absolute inset-0 flex items-center justify-center rounded-md bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity text-[10px] font-semibold text-white">
                      Inspect
                    </span>
                  </div>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold">{subject.displayName}</p>
                      {subject.thumbnail ? (
                        <Badge variant="outline" className="text-[10px] bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                          Photo Captured
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-muted-foreground">
                          Vector Only
                        </Badge>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {subject.captureCount} sightings · {subject.cameras.join(', ') || 'Camera 0'}
                    </p>
                    <p className="font-mono text-[11px] text-muted-foreground">
                      {formatTime(subject.firstSeen)} - {formatTime(subject.lastSeen)} IST · best {(subject.bestConfidence * 100).toFixed(1)}%
                    </p>
                    <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground/80">
                      Vector {subject.vectorDimension}D · SHA-256 {subject.representativeFingerprint.slice(0, 16)}...
                    </p>
                  </div>

                  <Button
                    size="icon"
                    variant="ghost"
                    title="Delete subject group"
                    aria-label={`Delete ${subject.displayName}`}
                    className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => {
                      if (window.confirm(`Delete ${subject.displayName} and all ${subject.captureCount} events?`)) {
                        deleteSubjectMutation.mutate(subject.id)
                      }
                    }}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button size="xs" onClick={() => openActionModal(subject, 'register')}>
                    <UserRoundPlus className="size-3.5 mr-1" /> Register Profile
                  </Button>
                  <Button size="xs" variant="outline" onClick={() => openActionModal(subject, 'assign')}>
                    <UsersRound className="size-3.5 mr-1" /> Assign to Existing
                  </Button>
                  <Button
                    size="xs"
                    variant="ghost"
                    onClick={() => {
                      const name = window.prompt('Rename subject', subject.displayName)
                      if (name?.trim()) renameMutation.mutate({ id: subject.id, name })
                    }}
                  >
                    <Pencil className="size-3 mr-1" /> Rename
                  </Button>

                  <select
                    aria-label={`Merge ${subject.displayName}`}
                    className="h-6 rounded-md border border-border bg-background px-2 text-xs text-muted-foreground hover:text-foreground"
                    defaultValue=""
                    onChange={(event) => {
                      if (event.target.value) {
                        mergeMutation.mutate({ id: subject.id, sourceId: event.target.value })
                        event.target.value = ''
                      }
                    }}
                  >
                    <option value="">Merge into group...</option>
                    {subjects
                      .filter((candidate) => candidate.id !== subject.id)
                      .map((candidate) => (
                        <option key={candidate.id} value={candidate.id}>
                          {candidate.displayName}
                        </option>
                      ))}
                  </select>
                </div>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  {subject.eventIds.slice(0, 8).map((eventId) => (
                    <Button
                      key={eventId}
                      size="xs"
                      variant="ghost"
                      title={`Delete event ${eventId}`}
                      className="font-mono text-[10px] text-muted-foreground hover:text-destructive"
                      onClick={() => {
                        if (window.confirm('Delete this event?')) {
                          deleteEventMutation.mutate({ subjectId: subject.id, eventId })
                        }
                      }}
                    >
                      {eventId.slice(0, 8)} <Trash2 className="size-2.5 ml-1" />
                    </Button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {selectedSubject && (
          <Dialog open={!!selectedSubject} onOpenChange={(open) => !open && setSelectedSubject(null)}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2 text-base">
                  <ScanFace className="size-5 text-rose-500" />
                  {modalMode === 'register' ? 'Register New Profile' : 'Assign to Existing Profile'}
                </DialogTitle>
                <DialogDescription>
                  Review the captured biometric photo and assign an identity without using CLI.
                </DialogDescription>
              </DialogHeader>

              <div className="my-2 grid grid-cols-1 items-center gap-4 sm:grid-cols-[130px_1fr] rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex flex-col items-center gap-1.5">
                  <FaceTile
                    image={selectedSubject.thumbnail}
                    tone="rose"
                    size="lg"
                    flagged
                    className="size-24 rounded-lg shadow-md ring-2 ring-primary/40"
                  />
                  <Badge variant="outline" className="text-[10px] font-mono">
                    {(selectedSubject.bestConfidence * 100).toFixed(1)}% confidence
                  </Badge>
                </div>

                <div className="space-y-1 text-xs text-muted-foreground">
                  <p className="font-semibold text-sm text-foreground">{selectedSubject.displayName}</p>
                  <p><span className="font-medium text-foreground">Captures:</span> {selectedSubject.captureCount} sightings</p>
                  <p><span className="font-medium text-foreground">Cameras:</span> {selectedSubject.cameras.join(', ') || 'Camera 0'}</p>
                  <p><span className="font-medium text-foreground">Time Recorded:</span> {formatTime(selectedSubject.firstSeen)} - {formatTime(selectedSubject.lastSeen)} IST</p>
                  <div className="flex gap-2 pt-2">
                    <Button
                      size="xs"
                      type="button"
                      variant={modalMode === 'register' ? 'default' : 'outline'}
                      onClick={() => setModalMode('register')}
                    >
                      Register New Profile
                    </Button>
                    <Button
                      size="xs"
                      type="button"
                      variant={modalMode === 'assign' ? 'default' : 'outline'}
                      onClick={() => setModalMode('assign')}
                    >
                      Assign to Profile
                    </Button>
                  </div>
                </div>
              </div>

              {modalMode === 'register' ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (!regName.trim()) return
                    registerMutation.mutate({
                      id: selectedSubject.id,
                      name: regName.trim(),
                      role: regRole,
                      department: regDept.trim() || undefined,
                    })
                  }}
                  className="space-y-3"
                >
                  <div className="space-y-1">
                    <Label htmlFor="reg-name" className="text-xs">Full Name *</Label>
                    <Input
                      id="reg-name"
                      required
                      autoFocus
                      placeholder="e.g. Alice Smith"
                      value={regName}
                      onChange={(e) => setRegName(e.target.value)}
                      className="h-8 text-xs"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor="reg-role" className="text-xs">Role</Label>
                      <select
                        id="reg-role"
                        value={regRole}
                        onChange={(e) => setRegRole(e.target.value as ProfileRole)}
                        className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
                      >
                        <option value="visitor">Visitor</option>
                        <option value="employee">Employee</option>
                        <option value="vip">VIP</option>
                        <option value="blacklist">Blacklist</option>
                        <option value="watchlist">Watchlist</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <Label htmlFor="reg-dept" className="text-xs">Department (Optional)</Label>
                      <Input
                        id="reg-dept"
                        placeholder="e.g. Engineering"
                        value={regDept}
                        onChange={(e) => setRegDept(e.target.value)}
                        className="h-8 text-xs"
                      />
                    </div>
                  </div>

                  <DialogFooter className="mt-4 gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => setSelectedSubject(null)}>
                      Cancel
                    </Button>
                    <Button type="submit" size="sm" disabled={!regName.trim() || registerMutation.isPending}>
                      {registerMutation.isPending ? 'Enrolling...' : 'Confirm & Register Profile'}
                    </Button>
                  </DialogFooter>
                </form>
              ) : (
                <div className="space-y-3">
                  <div className="space-y-1">
                    <Label htmlFor="assign-profile" className="text-xs">Select Target Profile</Label>
                    <select
                      id="assign-profile"
                      value={assignProfileId}
                      onChange={(e) => setAssignProfileId(e.target.value)}
                      className="h-8 w-full rounded-md border border-border bg-background px-2 text-xs"
                    >
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name} ({p.role}{p.department ? ` · ${p.department}` : ''})
                        </option>
                      ))}
                    </select>
                  </div>

                  <DialogFooter className="mt-4 gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => setSelectedSubject(null)}>
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      disabled={!assignProfileId || assignMutation.isPending}
                      onClick={() => {
                        if (assignProfileId) {
                          assignMutation.mutate({ id: selectedSubject.id, profileId: assignProfileId })
                        }
                      }}
                    >
                      {assignMutation.isPending ? 'Assigning...' : 'Assign to Profile'}
                    </Button>
                  </DialogFooter>
                </div>
              )}
            </DialogContent>
          </Dialog>
        )}
      </CardContent>
    </Card>
  )
}

export function ProfilesTab() {
  const queryClient = useQueryClient()
  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => fetchProfiles(),
  })
  const [role, setRole] = useState<'all' | ProfileRole>('all')
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'registered' | 'unregistered'>('registered')
  const updateMutation = useMutation({
    mutationFn: ({ profileId, name, role, department }: { profileId: string; name: string; role: ProfileRole; department: string }) => updateProfile(profileId, { name, role, department }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profiles'] }),
  })
  const deleteMutation = useMutation({
    mutationFn: deleteProfile,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profiles'] }),
  })
  const clearVectorsMutation = useMutation({
    mutationFn: deleteProfileEmbeddings,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profiles'] }),
  })

  const filtered = useMemo(() => {
    return profiles.filter((p) => {
      if (role !== 'all' && p.role !== role) return false
      if (query) {
        const q = query.toLowerCase()
        return (
          p.name.toLowerCase().includes(q) ||
          p.id.toLowerCase().includes(q) ||
          p.department.toLowerCase().includes(q)
        )
      }
      return true
    })
  }, [profiles, role, query])

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_360px]">
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/30 p-1">
          <Button size="sm" variant={view === 'registered' ? 'secondary' : 'ghost'} className="flex-1" onClick={() => setView('registered')}>
            Registered Vectors
          </Button>
          <Button size="sm" variant={view === 'unregistered' ? 'secondary' : 'ghost'} className="flex-1" onClick={() => setView('unregistered')}>
            Unregistered Vectors
          </Button>
        </div>
        {view === 'unregistered' ? <UnregisteredVectorsPanel profiles={profiles} /> : <Card className="gap-0 py-0">
          <CardHeader className="border-b border-border py-3">
            <SectionHeading
              icon={UsersRound}
              title="Enrolled Directory"
              count={filtered.length}
              description="Registered identities and their vector index status"
              action={<EnrolmentModal />}
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name / ID / department"
                className="h-8 w-60 text-xs"
              />
              <div className="flex flex-wrap gap-1.5">
                {ROLE_FILTERS.map((r) => (
                  <Button
                    key={r}
                    size="xs"
                    variant={role === r ? 'secondary' : 'ghost'}
                    className={cn('capitalize', role === r && 'ring-1 ring-inset ring-border')}
                    onClick={() => setRole(r)}
                  >
                    {r}
                  </Button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 2xl:grid-cols-4">
                {filtered.map((p) => (
                <ProfileCard key={p.id} profile={p} onSave={(changes) => updateMutation.mutate({ profileId: p.id, ...changes })} onClearVectors={() => { if (window.confirm(`Remove all ${p.embeddingCount} vectors for ${p.name}?`)) clearVectorsMutation.mutate(p.id) }} onDelete={() => { if (window.confirm(`Delete ${p.name} and its vectors? Historical detections will remain.`)) deleteMutation.mutate(p.id) }} />
              ))}
            </div>
          </CardContent>
        </Card>}
      </div>

      <DedupPanel />
    </div>
  )
}
