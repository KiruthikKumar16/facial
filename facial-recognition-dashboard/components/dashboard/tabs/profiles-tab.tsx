'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchDuplicates, fetchProfiles } from '@/lib/api'
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
import type { EmbeddingStatus, Profile, ProfileRole } from '@/lib/types'
import {
  CircleCheck,
  CircleDashed,
  CircleSlash,
  Copy,
  GitMerge,
  ImagePlus,
  TriangleAlert,
  UserRoundPlus,
  UsersRound,
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

function ProfileCard({ profile }: { profile: Profile }) {
  const meta = embeddingMeta[profile.embeddingStatus]
  const Icon = meta.icon
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
        <div>
          <p className="text-sm font-semibold">{profile.name}</p>
          <p className="font-mono text-[11px] text-muted-foreground">{profile.id}</p>
        </div>
        <RoleBadge role={profile.role} />
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
              {profile.lastSeen ? formatTime(profile.lastSeen) : '—'}
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

export function ProfilesTab() {
  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => fetchProfiles(),
  })
  const [role, setRole] = useState<'all' | ProfileRole>('all')
  const [query, setQuery] = useState('')

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
        <Card className="gap-0 py-0">
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
                <ProfileCard key={p.id} profile={p} />
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <DedupPanel />
    </div>
  )
}
