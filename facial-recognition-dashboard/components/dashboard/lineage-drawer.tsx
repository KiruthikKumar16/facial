'use client'

import { useQuery } from '@tanstack/react-query'
import { fetchProvenance } from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { formatTime } from '@/lib/format'
import {
  X,
  ShieldCheck,
  Cpu,
  Fingerprint,
  Users,
  Award,
  CloudUpload,
  Camera,
  Copy,
  Check,
  Workflow,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import { useState } from 'react'

export function LineageDrawer({
  eventId,
  onClose,
}: {
  eventId: string | null
  onClose: () => void
}) {
  const [copied, setCopied] = useState(false)

  const { data: prov, isLoading, isError, error } = useQuery({
    queryKey: ['provenance', eventId],
    queryFn: () => (eventId ? fetchProvenance(eventId) : null),
    enabled: !!eventId,
  })

  if (!eventId) return null

  const handleCopyHash = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-background/80 backdrop-blur-sm animate-in fade-in-0">
      <div className="relative flex h-full w-full max-w-xl flex-col border-l border-border bg-card shadow-2xl animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border p-4">
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Workflow className="size-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold tracking-tight">Event Decision Lineage</h2>
              <p className="font-mono text-xs text-muted-foreground truncate max-w-[320px]">
                {eventId}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground gap-3">
              <Loader2 className="size-8 animate-spin text-primary" />
              <p className="text-sm">Fetching mathematical decision graph...</p>
            </div>
          )}

          {isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-center">
              <AlertTriangle className="mx-auto size-6 text-destructive mb-2" />
              <p className="text-sm font-semibold text-destructive">Failed to load provenance record</p>
              <p className="text-xs text-muted-foreground mt-1">{(error as any)?.message || 'Record not found'}</p>
            </div>
          )}

          {prov && (
            <>
              {/* Provenance Chain Lock Banner */}
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="size-4 text-success" />
                    <span className="text-xs font-semibold uppercase tracking-wider text-foreground">
                      Cryptographic Chain Hash
                    </span>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 px-2 text-xs"
                    onClick={() => handleCopyHash(prov.provenanceChainHash)}
                  >
                    {copied ? <Check className="size-3 text-success" /> : <Copy className="size-3" />}
                    <span className="ml-1 font-mono text-[11px]">
                      {prov.provenanceChainHash.slice(0, 8)}...
                    </span>
                  </Button>
                </div>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground break-all">
                  {prov.provenanceChainHash}
                </p>
              </div>

              {/* 7-Stage Chronological Lineage Timeline */}
              <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                
                {/* 1. Camera Ingestion */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    1
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <Camera className="size-3.5 text-info" />
                      <span>1. Camera Ingestion</span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs font-mono text-muted-foreground">
                      <div>Camera: <span className="text-foreground">{prov.cameraId}</span></div>
                      <div>Config Version: <span className="text-foreground">v{prov.cameraConfigVersion}</span></div>
                    </div>
                  </div>
                </div>

                {/* 2. Frame Acquisition */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    2
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <Cpu className="size-3.5 text-warning" />
                      <span>2. Frame Acquisition</span>
                    </div>
                    <div className="mt-2 text-xs font-mono text-muted-foreground space-y-1">
                      <div>Frame Ref: <span className="text-foreground">{prov.frameReference}</span></div>
                      <div>Observations: <span className="text-foreground">{prov.observationCount} frames</span></div>
                    </div>
                  </div>
                </div>

                {/* 3. Face Tracking */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    3
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <Workflow className="size-3.5 text-primary" />
                      <span>3. Face Track Continuity</span>
                    </div>
                    <div className="mt-2 text-xs font-mono text-muted-foreground space-y-1">
                      <div>Track ID: <span className="text-foreground">{prov.trackId}</span></div>
                      <div className="text-[11px] text-muted-foreground">
                        Linked: {prov.observationReferences.slice(0, 3).join(', ')}
                        {prov.observationReferences.length > 3 ? ` +${prov.observationReferences.length - 3} more` : ''}
                      </div>
                    </div>
                  </div>
                </div>

                {/* 4. Embedding Fingerprint */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    4
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                        <Fingerprint className="size-3.5 text-destructive" />
                        <span>4. Embedding Fingerprint</span>
                      </div>
                      <Badge variant="outline" className="text-[10px] font-mono">
                        Privacy Protected
                      </Badge>
                    </div>
                    <div className="mt-2 text-xs font-mono text-muted-foreground space-y-1">
                      <div>Detector: <span className="text-foreground">{prov.detectionModelVersion}</span></div>
                      <div>Embedding Model: <span className="text-foreground">{prov.embeddingModelVersion}</span></div>
                      <div className="truncate">
                        SHA-256 Digest: <span className="text-primary">{prov.embeddingFingerprint}</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* 5. Candidate Evaluation */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    5
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <Users className="size-3.5 text-info" />
                      <span>5. Candidate Scoring</span>
                    </div>
                    <div className="mt-2 space-y-1.5">
                      {prov.candidateMatches.length > 0 ? (
                        prov.candidateMatches.map((cand, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between rounded bg-muted/50 px-2.5 py-1 text-xs font-mono"
                          >
                            <span className="text-foreground font-medium">#{cand.rank} {cand.identity}</span>
                            <span className="text-primary font-bold">{(cand.similarity * 100).toFixed(1)}%</span>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-muted-foreground italic">No candidates exceeded threshold</p>
                      )}
                    </div>
                  </div>
                </div>

                {/* 6. Recognition Decision */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    6
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <Award className="size-3.5 text-success" />
                      <span>6. Recognition Decision</span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs font-mono text-muted-foreground">
                      <div>Identity: <span className="text-foreground font-semibold">{prov.selectedIdentity}</span></div>
                      <div>Confidence: <span className="text-success font-bold">{(prov.confidence * 100).toFixed(1)}%</span></div>
                      <div>Tier: <span className="text-foreground">{prov.decisionTier}</span></div>
                      <div>Timestamp: <span className="text-foreground">{formatTime(prov.decisionTimestamp)}</span></div>
                    </div>
                  </div>
                </div>

                {/* 7. Cloud Sync */}
                <div className="relative">
                  <span className="absolute -left-6 top-1 flex size-5 items-center justify-center rounded-full border border-border bg-card text-[10px] font-bold">
                    7
                  </span>
                  <div className="rounded-lg border border-border bg-card p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                      <CloudUpload className="size-3.5 text-primary" />
                      <span>7. Cloud Synchronization</span>
                    </div>
                    <div className="mt-2 text-xs font-mono text-muted-foreground space-y-1">
                      <div>Cloud Record ID: <span className="text-foreground">{prov.cloudRecordId || 'synced'}</span></div>
                      <div>Event ID: <span className="text-foreground">{prov.eventId}</span></div>
                    </div>
                  </div>
                </div>

              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
