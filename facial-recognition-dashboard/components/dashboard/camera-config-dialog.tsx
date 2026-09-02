'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchCameraConfig, saveCameraConfig, rollbackCameraConfig } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { Camera, CameraConfigProfile } from '@/lib/types'
import {
  X,
  Sliders,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Layers,
} from 'lucide-react'

export function CameraConfigDialog({
  camera,
  onClose,
}: {
  camera: Camera | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<CameraConfigProfile | null>(null)
  const [feedback, setFeedback] = useState<string | null>(null)

  const { data: config, isLoading, isError } = useQuery({
    queryKey: ['camera-config', camera?.id],
    queryFn: () => (camera ? fetchCameraConfig(camera.id) : null),
    enabled: !!camera,
  })

  const saveMutation = useMutation({
    mutationFn: (newCfg: Partial<CameraConfigProfile>) =>
      saveCameraConfig(camera!.id, newCfg),
    onSuccess: (saved) => {
      setDraft(saved)
      setFeedback('Configuration successfully saved and activated on node.')
      queryClient.invalidateQueries({ queryKey: ['camera-config', camera?.id] })
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      setTimeout(() => setFeedback(null), 4000)
    },
    onError: (err: any) => {
      setFeedback(`Save failed: ${err.message || 'Unknown error'}`)
    },
  })

  const rollbackMutation = useMutation({
    mutationFn: () => rollbackCameraConfig(camera!.id),
    onSuccess: (rolledBack) => {
      setDraft(rolledBack)
      setFeedback(`Rolled back to version v${rolledBack.version}.`)
      queryClient.invalidateQueries({ queryKey: ['camera-config', camera?.id] })
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
      setTimeout(() => setFeedback(null), 4000)
    },
    onError: (err: any) => {
      setFeedback(`Rollback failed: ${err.message || 'Unknown error'}`)
    },
  })

  useEffect(() => {
    if (config) {
      setDraft(config)
    }
  }, [config])

  if (!camera) return null

  const isDirty =
    draft && config
      ? draft.detectionThreshold !== config.detectionThreshold ||
        draft.recognitionThreshold !== config.recognitionThreshold ||
        draft.qualityThreshold !== config.qualityThreshold ||
        draft.samplingRate !== config.samplingRate ||
        draft.temporalWindow !== config.temporalWindow
      : false

  const handleSave = () => {
    if (!draft) return
    saveMutation.mutate(draft)
  }

  const handleRollback = () => {
    if (confirm(`Roll back camera "${camera.name}" to its previous known configuration?`)) {
      rollbackMutation.mutate()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4 animate-in fade-in-0">
      <div className="relative flex w-full max-w-lg flex-col rounded-xl border border-border bg-card shadow-2xl animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border p-4">
          <div className="flex items-center gap-2.5">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sliders className="size-5" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold tracking-tight">{camera.name}</h2>
                {draft && (
                  <Badge variant="outline" className="font-mono text-[10px]">
                    v{draft.version}
                  </Badge>
                )}
              </div>
              <p className="font-mono text-xs text-muted-foreground">
                {camera.id} · {camera.zone}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        {/* Form Body */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {isLoading && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-2">
              <Loader2 className="size-6 animate-spin text-primary" />
              <p className="text-xs">Loading camera profile parameters...</p>
            </div>
          )}

          {isError && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-center text-xs text-destructive">
              <AlertTriangle className="mx-auto size-5 mb-1 text-destructive" />
              Failed to load camera configuration profile.
            </div>
          )}

          {draft && (
            <>
              {/* Detection Threshold */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-foreground">Detection Threshold</span>
                  <span className="font-mono text-primary">{Math.round(draft.detectionThreshold * 100)}%</span>
                </div>
                <Slider
                  value={[draft.detectionThreshold * 100]}
                  min={10}
                  max={99}
                  step={1}
                  onValueChange={([v]) => setDraft({ ...draft, detectionThreshold: v / 100 })}
                />
                <p className="text-[11px] text-muted-foreground">Minimum face detector confidence score</p>
              </div>

              {/* Recognition Threshold */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-foreground">Recognition Threshold</span>
                  <span className="font-mono text-primary">{Math.round(draft.recognitionThreshold * 100)}%</span>
                </div>
                <Slider
                  value={[draft.recognitionThreshold * 100]}
                  min={20}
                  max={99}
                  step={1}
                  onValueChange={([v]) => setDraft({ ...draft, recognitionThreshold: v / 100 })}
                />
                <p className="text-[11px] text-muted-foreground">Minimum cosine similarity to confirm identity match</p>
              </div>

              {/* Quality Threshold */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-foreground">Quality Assessment Filter</span>
                  <span className="font-mono text-primary">{Math.round(draft.qualityThreshold)} pts</span>
                </div>
                <Slider
                  value={[draft.qualityThreshold]}
                  min={10}
                  max={100}
                  step={1}
                  onValueChange={([v]) => setDraft({ ...draft, qualityThreshold: v })}
                />
                <p className="text-[11px] text-muted-foreground">Minimum face sharpness/pose score to accept frame embedding</p>
              </div>

              {/* Sampling Rate */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-foreground">Frame Sampling Rate</span>
                  <span className="font-mono text-primary">{(draft.samplingRate).toFixed(2)}x</span>
                </div>
                <Slider
                  value={[draft.samplingRate * 100]}
                  min={10}
                  max={100}
                  step={5}
                  onValueChange={([v]) => setDraft({ ...draft, samplingRate: v / 100 })}
                />
                <p className="text-[11px] text-muted-foreground">Edge processing frame stride (1.0 = full stream)</p>
              </div>

              {/* Temporal Window */}
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-foreground">Temporal Fusion Window</span>
                  <span className="font-mono text-primary">{(draft.temporalWindow).toFixed(1)}s</span>
                </div>
                <Slider
                  value={[draft.temporalWindow * 10]}
                  min={10}
                  max={100}
                  step={5}
                  onValueChange={([v]) => setDraft({ ...draft, temporalWindow: v / 10 })}
                />
                <p className="text-[11px] text-muted-foreground">Observation window for quality-weighted identity aggregation</p>
              </div>

              {/* Feedback Alert */}
              {feedback && (
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/60 p-2.5 text-xs">
                  <CheckCircle2 className="size-4 text-success shrink-0" />
                  <span className="text-foreground">{feedback}</span>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border p-4 bg-muted/20">
          <Button
            variant="outline"
            size="sm"
            onClick={handleRollback}
            disabled={!draft || draft.version <= 1 || rollbackMutation.isPending || saveMutation.isPending}
            className="gap-1.5 text-xs"
          >
            <RotateCcw className="size-3.5" />
            <span>Rollback (v{draft && draft.version > 1 ? draft.version - 1 : 1})</span>
          </Button>

          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!isDirty || saveMutation.isPending || rollbackMutation.isPending}
              className="gap-1.5"
            >
              {saveMutation.isPending ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <CheckCircle2 className="size-3.5" />
              )}
              <span>{saveMutation.isPending ? 'Saving...' : 'Save & Deploy'}</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
