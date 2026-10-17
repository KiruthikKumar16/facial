'use client';

import { useState, useEffect, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  scanCctvFootage,
  fetchLatestAuditReport,
  startBatchIngest,
  fetchIngestStatus,
  stopBatchIngest,
  fetchImportBatches,
  purgeImportBatch,
  fetchGpuStatus,
  browseDirectories,
  locateFolder,
  type VideoAuditReport,
  type IngestionProgress,
  type GpuStatusResponse,
  type BrowseDirectoryResponse,
  type DirectoryItem,
} from '@/lib/api';
import { ImportBatch } from '@/lib/types';
import { useDashboardMode } from '@/lib/mode-context';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { SectionHeading } from '@/components/dashboard/shared';
import { cn } from '@/lib/utils';
import {
  ShieldAlert,
  ShieldCheck,
  HardDrive,
  Play,
  Square,
  Search,
  FileCheck2,
  AlertTriangle,
  Clock,
  Video,
  Hash,
  Download,
  CheckCircle2,
  RefreshCw,
  FolderSearch,
  FolderOpen,
  Folder,
  ArrowUp,
  Film,
  Trash2,
  Layers,
  Filter,
  Database,
  Calendar,
  Check,
  X,
  Zap,
  Cpu,
  Activity,
  UserCheck,
  Radio,
  Smile,
} from 'lucide-react';

export function CctvAuditPanel() {
  const queryClient = useQueryClient();
  const { selectedBatchId, setSelectedBatchId } = useDashboardMode();
  const [directoryPath, setDirectoryPath] = useState<string>('D:\\DBGT POC');
  const [batchName, setBatchName] = useState<string>('DBGT POC Demo');
  const [sampleFps, setSampleFps] = useState<number>(2.0);
  const [tolerance, setTolerance] = useState<number>(5.0);
  const [motionGating, setMotionGating] = useState<boolean>(true);
  const [showManifest, setShowManifest] = useState<boolean>(false);
  const [confirmPurgeId, setConfirmPurgeId] = useState<string | null>(null);
  const [showFolderBrowser, setShowFolderBrowser] = useState<boolean>(false);
  const [browsePath, setBrowsePath] = useState<string>('D:\\');
  const [isNewIngestMode, setIsNewIngestMode] = useState<boolean>(false);
  const [showCompletionBanner, setShowCompletionBanner] = useState<boolean>(false);
  const [completedSummary, setCompletedSummary] = useState<IngestionProgress | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Directory browser query
  const { data: browseData, isLoading: isBrowsing } = useQuery<BrowseDirectoryResponse>({
    queryKey: ['video-audit-browse', browsePath],
    queryFn: () => browseDirectories(browsePath || undefined),
    enabled: showFolderBrowser,
  });

  const handleFolderSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const first = files[0];
      const relPath = first.webkitRelativePath || '';
      const topFolder = relPath.split('/')[0];
      if (topFolder) {
        try {
          const loc = await locateFolder(topFolder);
          if (loc.found && loc.path) {
            setDirectoryPath(loc.path);
            setBatchName(topFolder);
            return;
          }
        } catch {
          // fallback
        }
        setDirectoryPath(`D:\\${topFolder}`);
        setBatchName(topFolder);
      }
    }
  };

  // Poll for ingestion status every 500ms while running, else 4000ms
  const { data: ingestStatus, refetch: refetchStatus } = useQuery<IngestionProgress>({
    queryKey: ['video-ingest-status'],
    queryFn: fetchIngestStatus,
    refetchInterval: (query) => {
      return query.state.data?.running ? 500 : 4000;
    },
  });

  // Real-time GPU & VRAM telemetry query
  const { data: gpuStatus } = useQuery<GpuStatusResponse>({
    queryKey: ['video-audit-gpu-status'],
    queryFn: fetchGpuStatus,
    refetchInterval: ingestStatus?.running ? 5000 : 15000,
  });

  // Cached audit report
  const { data: auditReport, refetch: refetchReport, isLoading: isReportLoading } = useQuery<VideoAuditReport>({
    queryKey: ['video-audit-latest'],
    queryFn: fetchLatestAuditReport,
    retry: false,
  });

  // Ingested batches query
  const { data: importBatches, isLoading: isBatchesLoading } = useQuery<ImportBatch[]>({
    queryKey: ['import-batches'],
    queryFn: fetchImportBatches,
    refetchInterval: (query) => {
      return ingestStatus?.running ? 3000 : 15000;
    },
  });

  // Active batch object
  const activeBatch = importBatches?.find((b) => b.id === selectedBatchId);

  // Auto-select first batch if none is selected and not in explicit new ingest mode
  useEffect(() => {
    if (!selectedBatchId && !isNewIngestMode && importBatches && importBatches.length > 0) {
      const first = importBatches[0];
      setSelectedBatchId(first.id);
      setBatchName(first.name);
      if (first.sourceDirectory) {
        const winPath = first.sourceDirectory
          .replace(/^\/([a-zA-Z])\//, '$1:\\')
          .replace(/\//g, '\\');
        setDirectoryPath(winPath);
      }
    }
  }, [importBatches, selectedBatchId, isNewIngestMode, setSelectedBatchId]);

  // Scan mutation
  const scanMutation = useMutation({
    mutationFn: () =>
      scanCctvFootage({
        directory: directoryPath,
        tolerance_seconds: tolerance,
        compute_hashes: true,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(['video-audit-latest'], data);
    },
  });

  // Ingest mutation
  const ingestMutation = useMutation({
    mutationFn: () =>
      startBatchIngest({
        directory: directoryPath,
        sample_fps: sampleFps,
        batch_name: batchName || undefined,
        enable_motion_gating: motionGating,
      }),
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
    },
  });

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: stopBatchIngest,
    onSuccess: () => {
      refetchStatus();
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
    },
  });

  // Purge batch mutation
  const purgeMutation = useMutation({
    mutationFn: (batchId: string) => purgeImportBatch(batchId),
    onSuccess: (_, batchId) => {
      if (selectedBatchId === batchId) {
        setSelectedBatchId(null);
      }
      setConfirmPurgeId(null);
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['face-logs'] });
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['kpis'] });
      queryClient.invalidateQueries({ queryKey: ['footfall'] });
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      queryClient.invalidateQueries({ queryKey: ['gender-distribution'] });
    },
    onError: () => {
      setConfirmPurgeId(null);
    },
  });

  const isScanning = scanMutation.isPending;
  const isIngesting = (ingestStatus?.running ?? false) || ingestMutation.isPending;
  const report = scanMutation.data || auditReport;

  // Track completion transition and update cache
  const prevRunningRef = useRef(false);
  useEffect(() => {
    if (prevRunningRef.current && !ingestStatus?.running && ingestStatus?.completed) {
      setShowCompletionBanner(true);
      setCompletedSummary(ingestStatus);
      queryClient.invalidateQueries({ queryKey: ['import-batches'] });
      queryClient.invalidateQueries({ queryKey: ['face-logs'] });
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['kpis'] });
      queryClient.invalidateQueries({ queryKey: ['footfall'] });
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      queryClient.invalidateQueries({ queryKey: ['gender-distribution'] });
    }
    prevRunningRef.current = ingestStatus?.running ?? false;
  }, [ingestStatus, queryClient]);

  const handleDownloadReport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cctv_security_audit_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card className="gap-0 py-0 border-border/60 bg-card/40 backdrop-blur-xl shadow-2xl">
      <CardHeader className="border-b border-border/60 py-4 px-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary ring-1 ring-inset ring-primary/20">
            <HardDrive className="size-5" />
          </span>
          <div>
            <CardTitle className="text-base font-semibold tracking-tight flex items-center gap-2">
              Standalone CCTV Hard Disk Audit & Ingestion
              <Badge variant="outline" className="text-[10px] uppercase font-mono tracking-wider border-primary/30 text-primary">
                Client POC Mode
              </Badge>
            </CardTitle>
            <CardDescription className="text-xs text-muted-foreground mt-0.5">
              Verify 3-day footage continuity, detect deleted/trimmed time clips, and batch-ingest facial recognition timeline
            </CardDescription>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {gpuStatus && (
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-muted-foreground bg-background/60 px-2.5 py-1 rounded-md border border-border/60">
              <Cpu className="size-3.5 text-primary" />
              <span>
                {gpuStatus.device === 'gpu' && gpuStatus.vram_info?.total_mb > 0
                  ? `${gpuStatus.gpu_name || 'GPU'}: ${(gpuStatus.vram_info.free_mb / 1024).toFixed(1)}GB Free (${(gpuStatus.live_reserve_mb / 1024).toFixed(1)}GB Reserve) • ${gpuStatus.safe_workers_recommended} Workers`
                  : `CPU Ingest Engine (${gpuStatus.cpu_cores || 8} Cores) • ${gpuStatus.safe_workers_recommended} Parallel Workers`}
              </span>
            </div>
          )}

          {report && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadReport}
              className="h-8 gap-1.5 text-xs font-mono"
            >
              <Download className="size-3.5" />
              <span>Export Audit Manifest</span>
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="p-6 space-y-6">
        {/* Controls Bar */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-[1.3fr_1.1fr_auto_auto] gap-4 items-start rounded-lg border border-border/50 bg-background/50 p-4">
          {/* Column 1: Footage Path */}
          <div className="space-y-1.5 relative">
            <div className="flex items-center justify-between h-5">
              <Label htmlFor="cctv-dir" className="text-xs font-medium text-foreground flex items-center gap-1.5">
                <FolderSearch className="size-3.5 text-primary" />
                <span>Hard Disk CCTV Footage Path</span>
              </Label>
              <div className="flex items-center gap-1.5">
                <button
                  id="btn-quick-dbgt-poc"
                  type="button"
                  onClick={() => {
                    setDirectoryPath('D:\\DBGT POC');
                    if (!batchName) setBatchName('DBGT POC Demo');
                  }}
                  className={cn(
                    "px-1.5 py-0.5 rounded font-mono text-[10px] border transition-colors",
                    directoryPath === 'D:\\DBGT POC'
                      ? "bg-primary/20 border-primary text-primary font-semibold"
                      : "bg-background/60 border-border/60 text-muted-foreground hover:text-foreground"
                  )}
                  title="Quick fill D:\DBGT POC"
                >
                  Quick: D:\DBGT POC
                </button>
                <button
                  type="button"
                  onClick={() => setShowFolderBrowser(!showFolderBrowser)}
                  className="text-[11px] font-mono text-primary hover:underline flex items-center gap-1"
                >
                  <Folder className="size-3" />
                  <span>{showFolderBrowser ? 'Close' : 'Browse Drives'}</span>
                </button>
              </div>
            </div>

            <div className="flex items-center gap-1.5 h-9">
              <Input
                id="cctv-dir"
                placeholder="e.g. D:\DBGT POC or D:\footage"
                value={directoryPath}
                onChange={(e) => setDirectoryPath(e.target.value)}
                className="font-mono text-xs bg-card/60 flex-1 h-9"
                disabled={isScanning || isIngesting}
              />

              <input
                ref={folderInputRef}
                type="file"
                {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
                multiple
                className="hidden"
                onChange={handleFolderSelect}
              />

              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => folderInputRef.current?.click()}
                className="h-9 px-3 text-xs gap-1.5 shrink-0 bg-card/80 border-border/80 hover:bg-card"
                disabled={isScanning || isIngesting}
                title="Select folder from your computer"
              >
                <FolderOpen className="size-3.5 text-primary" />
                <span>Select Folder</span>
              </Button>
            </div>

            {/* Interactive Directory Browser Modal */}
            {showFolderBrowser && (
              <div className="absolute left-0 top-full mt-2 z-50 w-full min-w-[340px] max-w-lg rounded-lg border border-border/80 bg-popover/95 backdrop-blur-xl shadow-2xl p-3.5 space-y-3 animate-in fade-in zoom-in-95 duration-150">
                <div className="flex items-center justify-between border-b border-border/40 pb-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <Folder className="size-4 text-primary shrink-0" />
                    <span className="text-xs font-semibold truncate text-foreground font-mono">
                      {browsePath ? browsePath : 'Available Drives'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    {browseData?.parent_path && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setBrowsePath(browseData.parent_path || '')}
                        className="h-6 px-1.5 text-[10px] gap-1 font-mono"
                        title="Go up one folder"
                      >
                        <ArrowUp className="size-3" />
                        <span>Up</span>
                      </Button>
                    )}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowFolderBrowser(false)}
                      className="h-6 px-1.5 text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      <X className="size-3" />
                    </Button>
                  </div>
                </div>

                {isBrowsing ? (
                  <div className="py-6 text-center text-xs text-muted-foreground font-mono flex items-center justify-center gap-2">
                    <RefreshCw className="size-3.5 animate-spin text-primary" /> Scanning folders...
                  </div>
                ) : !browseData?.items || browseData.items.length === 0 ? (
                  <div className="py-4 text-center text-xs text-muted-foreground font-mono">
                    No accessible subdirectories found in this path.
                  </div>
                ) : (
                  <div className="max-h-60 overflow-y-auto space-y-1 pr-1 font-mono text-xs">
                    {browseData.items.map((item, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between p-1.5 rounded hover:bg-muted/40 transition-colors group"
                      >
                        <button
                          type="button"
                          onClick={() => {
                            setBrowsePath(item.path);
                          }}
                          className="flex items-center gap-2 text-left truncate flex-1 mr-2 text-foreground/90 hover:text-primary"
                        >
                          {item.has_videos ? (
                            <Film className="size-3.5 text-success shrink-0" />
                          ) : (
                            <Folder className="size-3.5 text-primary/70 shrink-0" />
                          )}
                          <span className="truncate">{item.name}</span>
                          {item.has_videos && (
                            <Badge variant="outline" className="text-[9px] px-1 py-0 border-success/40 text-success">
                              Footage Found
                            </Badge>
                          )}
                        </button>

                        <Button
                          type="button"
                          size="sm"
                          variant="secondary"
                          onClick={() => {
                            setDirectoryPath(item.path);
                            setShowFolderBrowser(false);
                            if (!batchName || batchName === 'CCTV 3-Day Archive') {
                              setBatchName(item.name.replace(/[:\\/]/g, ' ').trim() || 'CCTV Batch');
                            }
                          }}
                          className="h-6 px-2 text-[10px] shrink-0 opacity-80 group-hover:opacity-100"
                        >
                          Select
                        </Button>
                      </div>
                    ))}
                  </div>
                )}

                {browsePath && (
                  <div className="pt-2 border-t border-border/40 flex items-center justify-between">
                    <span className="text-[10px] text-muted-foreground font-mono truncate max-w-[200px]">
                      Path: {browsePath}
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => {
                        setDirectoryPath(browsePath);
                        setShowFolderBrowser(false);
                      }}
                      className="h-6 text-[10px] px-2.5 font-mono"
                    >
                      Use this folder
                    </Button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Column 2: Imported Archive Dataset Dropdown */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between h-5">
              <Label htmlFor="batch-select" className="text-xs font-medium text-foreground flex items-center gap-1.5">
                <Database className="size-3.5 text-primary" />
                <span>Imported Archive Dataset</span>
              </Label>
              <div className="flex items-center gap-1.5">
                <Badge variant="outline" className="text-[10px] font-mono px-1.5 py-0 border-border/70 text-muted-foreground">
                  {importBatches?.length ?? 0} {importBatches?.length === 1 ? 'batch' : 'batches'}
                </Badge>
                {!isNewIngestMode && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsNewIngestMode(true);
                      setSelectedBatchId(null);
                      setBatchName('');
                    }}
                    className="text-[10px] font-mono text-primary hover:underline flex items-center gap-0.5"
                    title="Switch to new ingestion mode"
                  >
                    <span>➕ New</span>
                  </button>
                )}
              </div>
            </div>

            <div className="flex items-center gap-1.5 h-9">
              {isNewIngestMode ? (
                <div className="flex items-center gap-1.5 w-full h-9">
                  <Input
                    id="batch-name"
                    placeholder="New batch tag e.g. Warehouse CCTV Day 1"
                    value={batchName}
                    onChange={(e) => setBatchName(e.target.value)}
                    className="font-mono text-xs bg-card/60 flex-1 h-9"
                    disabled={isScanning || isIngesting}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setIsNewIngestMode(false);
                      if (importBatches && importBatches.length > 0) {
                        const first = importBatches[0];
                        setSelectedBatchId(first.id);
                        setBatchName(first.name);
                        if (first.sourceDirectory) {
                          const winPath = first.sourceDirectory
                            .replace(/^\/([a-zA-Z])\//, '$1:\\')
                            .replace(/\//g, '\\');
                          setDirectoryPath(winPath);
                        }
                      }
                    }}
                    className="h-9 px-2 text-[10px] font-mono shrink-0 text-muted-foreground hover:text-foreground"
                    title="Select from imported datasets"
                  >
                    Select Batch
                  </Button>
                </div>
              ) : (
                <select
                  id="batch-select"
                  value={selectedBatchId || '__new__'}
                  onChange={(e) => {
                    const val = e.target.value;
                    if (val === '__new__') {
                      setIsNewIngestMode(true);
                      setSelectedBatchId(null);
                      setBatchName('');
                    } else {
                      setIsNewIngestMode(false);
                      setSelectedBatchId(val);
                      const found = importBatches?.find((b) => b.id === val);
                      if (found) {
                        setBatchName(found.name);
                        if (found.sourceDirectory) {
                          const winPath = found.sourceDirectory
                            .replace(/^\/([a-zA-Z])\//, '$1:\\')
                            .replace(/\//g, '\\');
                          setDirectoryPath(winPath);
                        }
                      }
                    }
                  }}
                  className="h-9 w-full rounded-md border border-input bg-card/60 px-3 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  disabled={isScanning || isIngesting}
                >
                  <option value="__new__">➕ Ingest New CCTV Dataset...</option>
                  {importBatches && importBatches.length > 0 && (
                    <optgroup label="Imported Archive Datasets">
                      {importBatches.map((b) => (
                        <option key={b.id} value={b.id}>
                          {b.name} ({b.totalDetections} det · {b.cameraCount} cam · {b.totalFiles} files)
                        </option>
                      ))}
                    </optgroup>
                  )}
                </select>
              )}
            </div>
          </div>

          {/* Column 3: Forensic & Tuning Controls */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="space-y-1.5">
              <div className="h-5 flex items-center">
                <Label htmlFor="tolerance-sec" className="text-xs text-muted-foreground">
                  Gap Tolerance (s)
                </Label>
              </div>
              <div className="h-9 flex items-center">
                <Input
                  id="tolerance-sec"
                  type="number"
                  min="1"
                  max="60"
                  value={tolerance}
                  onChange={(e) => setTolerance(Number(e.target.value))}
                  className="w-20 text-xs font-mono h-9 bg-card/60"
                  disabled={isScanning || isIngesting}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="h-5 flex items-center">
                <Label htmlFor="sample-fps" className="text-xs text-muted-foreground">
                  Sampling Rate
                </Label>
              </div>
              <div className="h-9 flex items-center">
                <select
                  id="sample-fps"
                  value={sampleFps}
                  onChange={(e) => setSampleFps(Number(e.target.value))}
                  className="h-9 rounded-md border border-input bg-card/60 px-3 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  disabled={isScanning || isIngesting}
                >
                  <option value={2}>2 FPS (Ultra Fast 15x)</option>
                  <option value={3}>3 FPS (Recommended 10x)</option>
                  <option value={5}>5 FPS (Dense 6x)</option>
                  <option value={10}>10 FPS (High Precision)</option>
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="h-5 flex items-center">
                <Label className="text-xs text-muted-foreground">
                  AI Optimization
                </Label>
              </div>
              <div className="h-9 flex items-center">
                <button
                  type="button"
                  onClick={() => setMotionGating(!motionGating)}
                  disabled={isScanning || isIngesting}
                  className={cn(
                    "h-9 px-3 rounded-md text-xs font-medium border flex items-center gap-1.5 transition-colors font-mono",
                    motionGating
                      ? "bg-primary/10 border-primary/40 text-primary hover:bg-primary/20"
                      : "bg-muted/40 border-input text-muted-foreground hover:bg-muted/60"
                  )}
                  title="Skips static night footage while preserving stationary people with 3s cooldown & 5s anchor checks"
                >
                  <Zap className={cn("size-3.5", motionGating ? "fill-primary text-primary" : "text-muted-foreground")} />
                  <span>Motion Gate: {motionGating ? "ON" : "OFF"}</span>
                </button>
              </div>
            </div>
          </div>

          {/* Column 4: Execution Pipeline Actions */}
          <div className="space-y-1.5">
            <div className="h-5 flex items-center">
              <span className="text-[11px] font-mono uppercase text-muted-foreground tracking-wider">
                Pipeline Execution
              </span>
            </div>
            <div className="flex items-center gap-2 h-9">
              <Button
                id="btn-run-security-audit"
                onClick={() => scanMutation.mutate()}
                disabled={isScanning || isIngesting || !directoryPath}
                variant="outline"
                className="h-9 gap-1.5 border-primary/40 hover:bg-primary/10 text-primary font-medium text-xs shrink-0"
              >
                {isScanning ? (
                  <RefreshCw className="size-3.5 animate-spin" />
                ) : (
                  <FileCheck2 className="size-3.5" />
                )}
                <span>{isScanning ? 'Auditing...' : 'Run Security Audit'}</span>
              </Button>

              {!isIngesting ? (
                <Button
                  id="btn-ingest-face-recognition"
                  onClick={() => ingestMutation.mutate()}
                  disabled={isScanning || isIngesting || !directoryPath}
                  className="h-9 gap-1.5 bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 shrink-0"
                >
                  <Play className="size-3.5 fill-current" />
                  <span>Ingest Face Recognition</span>
                </Button>
              ) : (
                <Button
                  id="btn-stop-ingest"
                  onClick={() => stopMutation.mutate()}
                  variant="destructive"
                  className="h-9 gap-1.5 font-medium text-xs shrink-0"
                >
                  <Square className="size-3.5 fill-current" />
                  <span>Stop Ingest</span>
                </Button>
              )}
            </div>
          </div>
        </div>

        {/* Scan Error Notice */}
        {scanMutation.isError && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            <span>Scan Failed: {(scanMutation.error as Error).message}</span>
          </div>
        )}

        {/* Ingest Error Notice */}
        {ingestMutation.isError && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            <span>Ingestion Failed: {(ingestMutation.error as Error).message}</span>
          </div>
        )}

        {/* Dynamic Real-Time Ingestion Progress & Telemetry Mission Control */}
        {isIngesting && (
          <div className="rounded-xl border border-primary/50 bg-gradient-to-b from-primary/10 via-background/80 to-background/60 p-5 space-y-4 shadow-2xl backdrop-blur-xl relative overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Top ambient glowing line */}
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-primary to-transparent animate-pulse" />

            {/* Header: Status Beacon & Quick Actions */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
              <div className="flex items-center gap-3">
                <span className="relative flex size-3.5">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-80" />
                  <span className="relative inline-flex size-3.5 rounded-full bg-primary shadow-[0_0_12px_var(--primary)]" />
                </span>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-primary flex items-center gap-1.5 font-mono">
                      <Radio className="size-3.5 animate-pulse text-primary" />
                      Live AI Facial Recognition Ingestion Pipeline
                    </h4>
                    <Badge variant="outline" className="text-[10px] font-mono px-2 py-0 border-primary/40 bg-primary/10 text-primary animate-pulse">
                      Active Stream Ingestion
                    </Badge>
                  </div>
                  <p className="text-[11px] font-mono text-muted-foreground mt-0.5 flex items-center gap-2 truncate">
                    <span className="text-foreground font-semibold flex items-center gap-1">
                      <Film className="size-3 text-primary" />
                      {ingestStatus?.current_file ? ingestStatus.current_file : `Allocating ${gpuStatus?.device === 'gpu' ? 'GPU' : 'CPU'} workers & initializing frame decoder...`}
                    </span>
                    {ingestStatus?.current_camera && (
                      <>
                        <span>•</span>
                        <span className="text-primary font-semibold">Camera: {ingestStatus.current_camera}</span>
                      </>
                    )}
                  </p>
                </div>
              </div>

              {/* Hardware & Emergency Controls */}
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="outline" className="font-mono text-[10px] border-border/60 bg-background/60 text-muted-foreground flex items-center gap-1">
                  <Cpu className="size-3 text-primary" />
                  {ingestStatus?.active_workers ?? 1} Parallel Workers
                </Badge>
                {motionGating && (
                  <Badge variant="outline" className="font-mono text-[10px] border-amber-500/40 bg-amber-500/10 text-amber-400 flex items-center gap-1">
                    <Zap className="size-3 fill-amber-400" />
                    Motion Gated
                  </Badge>
                )}
                <Button
                  onClick={() => stopMutation.mutate()}
                  variant="destructive"
                  size="sm"
                  className="h-7 text-xs gap-1.5 font-mono font-medium shadow-sm hover:bg-destructive/90"
                >
                  <Square className="size-3 fill-current" />
                  <span>Stop Pipeline</span>
                </Button>
              </div>
            </div>

            {/* Dynamic Multi-Level Animated Progress Bar */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-2 text-foreground font-semibold">
                  <span className="text-primary">
                    File {ingestStatus?.file_index || 0} of {ingestStatus?.total_files || 1}
                  </span>
                  <span className="text-muted-foreground text-[11px]">
                    ({(ingestStatus?.frames_processed || 0).toLocaleString()} / {ingestStatus?.total_estimated_frames ? ingestStatus.total_estimated_frames.toLocaleString() : 'Estimating...'} frames decoded)
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-extrabold text-primary tracking-tight font-mono">
                    {(ingestStatus?.progress_percent || 0).toFixed(1)}%
                  </span>
                </div>
              </div>

              {/* Glowing Multi-Color Progress Track */}
              <div className="h-3.5 w-full overflow-hidden rounded-full bg-background/80 shadow-inner border border-border/60 relative">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary via-cyan-400 to-emerald-400 transition-all duration-300 ease-out relative"
                  style={{ width: `${Math.max(2, Math.min(100, ingestStatus?.progress_percent || 0))}%` }}
                >
                  {/* Subtle animated light sweep */}
                  <div className="absolute inset-0 bg-[linear-gradient(90deg,transparent_0%,rgba(255,255,255,0.3)_50%,transparent_100%)] animate-shimmer" />
                </div>
              </div>
            </div>

            {/* Live Telemetry Metric KPI Cards (6 real-time metrics) */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 font-mono">
              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <Zap className="size-3 text-primary" /> Speed
                </span>
                <p className="text-base font-bold text-foreground">
                  {(ingestStatus?.processing_fps || 0).toFixed(1)} <span className="text-[10px] font-normal text-muted-foreground">FPS</span>
                </p>
                <p className="text-[9px] text-primary truncate">
                  ⚡ {(Number(ingestStatus?.processing_fps || 0) / Number(ingestStatus?.sample_fps || sampleFps || 2)).toFixed(1)}x Realtime Speed
                </p>
              </div>

              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <UserCheck className="size-3 text-success" /> Faces Found
                </span>
                <p className="text-base font-bold text-success">
                  {(ingestStatus?.faces_detected || 0).toLocaleString()}
                </p>
                <p className="text-[9px] text-muted-foreground truncate">
                  ArcFace 512-D Vectors
                </p>
              </div>

              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <Film className="size-3 text-cyan-400" /> Frames
                </span>
                <p className="text-base font-bold text-foreground">
                  {(ingestStatus?.frames_processed || 0).toLocaleString()}
                </p>
                <p className="text-[9px] text-muted-foreground truncate">
                  Sampled @ {ingestStatus?.sample_fps ?? sampleFps} FPS
                </p>
              </div>

              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <Activity className="size-3 text-amber-400" /> Static Skipped
                </span>
                <p className="text-base font-bold text-amber-400">
                  {((ingestStatus?.static_frames_skipped || 0)).toLocaleString()}
                </p>
                <p className="text-[9px] text-muted-foreground truncate">
                  Motion Gating Saved
                </p>
              </div>

              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <Clock className="size-3 text-sky-400" /> ETA
                </span>
                <p className="text-base font-bold text-foreground">
                  {ingestStatus?.eta_seconds && ingestStatus.eta_seconds > 0
                    ? (ingestStatus.eta_seconds > 60
                        ? `${Math.round(ingestStatus.eta_seconds / 60)}m ${Math.round(ingestStatus.eta_seconds % 60)}s`
                        : `${Math.round(ingestStatus.eta_seconds)}s`)
                    : 'Calculating...'}
                </p>
                <p className="text-[9px] text-muted-foreground truncate">
                  Elapsed: {Math.floor((ingestStatus?.elapsed_seconds || 0) / 60)}m {Math.round((ingestStatus?.elapsed_seconds || 0) % 60)}s
                </p>
              </div>

              <div className="rounded-lg border border-border/50 bg-background/50 p-2.5 space-y-1">
                <span className="text-[10px] text-muted-foreground uppercase flex items-center gap-1 font-semibold">
                  <ShieldAlert className="size-3 text-destructive" /> Alerts
                </span>
                <p className={cn("text-base font-bold", (ingestStatus?.alerts_triggered || 0) > 0 ? "text-destructive" : "text-foreground")}>
                  {ingestStatus?.alerts_triggered ?? 0}
                </p>
                <p className="text-[9px] text-muted-foreground truncate">
                  Watchlist Matches
                </p>
              </div>
            </div>

            {/* Live Processing Activity Stream Ticker */}
            <div className="flex items-center justify-between text-[11px] font-mono bg-background/40 rounded px-3 py-1.5 border border-border/40 text-muted-foreground">
              <div className="flex items-center gap-2 truncate">
                <span className="size-1.5 rounded-full bg-success animate-ping shrink-0" />
                <span className="truncate">
                  STREAM DECODER ACTIVE: {ingestStatus?.current_file || 'Awaiting stream'} • InsightFace Buffalo_S Vector Embeddings
                </span>
              </div>
              <span className="text-[10px] text-primary/80 shrink-0 hidden sm:inline flex items-center gap-1 font-mono">
                {gpuStatus?.device === 'gpu' && gpuStatus.vram_info?.total_mb > 0 ? (
                  <>
                    <Zap className="size-3 text-emerald-400" />
                    GPU VRAM Reserve: {(gpuStatus.live_reserve_mb / 1024).toFixed(1)} GB Protected
                  </>
                ) : (
                  <>
                    <Cpu className="size-3 text-primary" />
                    Multi-Threaded CPU Engine • Dynamic Resource Management
                  </>
                )}
              </span>
            </div>
          </div>
        )}

        {/* Celebratory Ingestion Complete Summary Card */}
        {showCompletionBanner && !isIngesting && completedSummary && (
          <div className="rounded-xl border border-success/40 bg-success/10 p-4 space-y-3 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-success/20 text-success border border-success/40 shrink-0">
                  <CheckCircle2 className="size-5" />
                </span>
                <div>
                  <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                    Batch Facial Recognition Ingestion Completed!
                    <Badge variant="outline" className="text-[10px] font-mono border-success/40 bg-success/10 text-success">
                      100% Processed
                    </Badge>
                  </h4>
                  <p className="text-xs text-muted-foreground font-mono mt-0.5">
                    Analyzed {completedSummary.frames_processed.toLocaleString()} frames across {completedSummary.total_files} files • Found {completedSummary.faces_detected.toLocaleString()} face detections ({completedSummary.alerts_triggered} alerts) in {Math.round(completedSummary.elapsed_seconds)}s.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCompletionBanner(false)}
                  className="h-8 text-xs font-mono"
                >
                  Dismiss
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Selected Dataset Security Audit Header & Overview */}
        {activeBatch && (
          <div className="rounded-lg border border-border/70 bg-card/60 p-4 space-y-3 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/40 pb-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary border border-primary/20 shrink-0">
                  <ShieldCheck className="size-5" />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-bold text-foreground font-mono tracking-tight truncate" title={activeBatch.name}>
                      {activeBatch.name}
                    </h3>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-[10px] font-mono uppercase px-2 py-0.5',
                        activeBatch.status === 'completed'
                          ? 'text-success border-success/40 bg-success/10'
                          : activeBatch.status === 'processing'
                          ? 'text-primary border-primary/40 bg-primary/10 animate-pulse'
                          : 'text-muted-foreground border-border'
                      )}
                    >
                      {activeBatch.status}
                    </Badge>
                    <Badge className="text-[10px] bg-primary/15 text-primary border border-primary/30 font-mono">
                      Active Dataset Audit
                    </Badge>
                  </div>
                  <p className="text-[11px] font-mono text-muted-foreground mt-0.5 flex items-center gap-2 truncate">
                    <span className="truncate">📁 {activeBatch.sourceDirectory}</span>
                    <span>•</span>
                    <span className="shrink-0">ID: {activeBatch.id.slice(0, 16)}...</span>
                  </p>
                </div>
              </div>

              {/* Actions row for the active dataset */}
              <div className="flex items-center gap-2 flex-wrap shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => scanMutation.mutate()}
                  disabled={isScanning || isIngesting || !directoryPath}
                  className="h-8 text-xs gap-1.5 font-mono border-primary/40 hover:bg-primary/10 text-primary"
                >
                  <RefreshCw className={cn("size-3.5", isScanning && "animate-spin")} />
                  <span>{isScanning ? 'Auditing...' : 'Re-Run Security Audit'}</span>
                </Button>

                {report && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDownloadReport}
                    className="h-8 text-xs gap-1.5 font-mono bg-card/60"
                  >
                    <Download className="size-3.5" />
                    <span>Export Manifest</span>
                  </Button>
                )}

                {confirmPurgeId === activeBatch.id ? (
                  <div className="flex items-center gap-1.5 animate-in fade-in duration-200">
                    <span className="text-[11px] text-destructive font-semibold">Purge dataset?</span>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={purgeMutation.isPending}
                      onClick={() => purgeMutation.mutate(activeBatch.id)}
                      className="h-8 px-2.5 text-xs font-mono"
                    >
                      {purgeMutation.isPending ? 'Purging...' : 'Confirm'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={purgeMutation.isPending}
                      onClick={() => setConfirmPurgeId(null)}
                      className="h-8 px-2 text-xs"
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setConfirmPurgeId(activeBatch.id)}
                    className="h-8 text-xs gap-1 text-destructive hover:text-destructive hover:bg-destructive/10 font-mono"
                    title="Purge only this test batch without touching live records"
                  >
                    <Trash2 className="size-3.5" />
                    <span>Purge Dataset</span>
                  </Button>
                )}
              </div>
            </div>

            {/* Quick Dataset Summary Stats Row */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-center font-mono text-xs bg-background/40 rounded-lg p-2.5 border border-border/40">
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Face Detections</span>
                <span className="text-base font-bold text-foreground">{activeBatch.totalDetections.toLocaleString()}</span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Security Alerts</span>
                <span className={cn('text-base font-bold', activeBatch.totalAlerts > 0 ? 'text-destructive' : 'text-success')}>
                  {activeBatch.totalAlerts}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Active Cameras</span>
                <span className="text-base font-bold text-foreground">{activeBatch.cameraCount}</span>
              </div>
              <div>
                <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Footage Files</span>
                <span className="text-base font-bold text-foreground">{activeBatch.totalFiles}</span>
              </div>
            </div>
          </div>
        )}

        {/* Security Audit Loading State */}
        {isScanning && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-8 text-center space-y-3 animate-pulse">
            <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary mx-auto ring-1 ring-primary/30">
              <RefreshCw className="size-6 animate-spin text-primary" />
            </div>
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-foreground">Forensic CCTV Security Audit in Progress...</h4>
              <p className="text-xs text-muted-foreground font-mono max-w-md mx-auto">
                Scanning footage stream, verifying timeline continuity, container integrity, and calculating cryptographic SHA-256 signatures for {directoryPath}
              </p>
            </div>
          </div>
        )}

        {/* Security Audit Ready Empty State (if not scanned yet) */}
        {!report && !isScanning && (
          <div className="rounded-lg border border-dashed border-border/80 bg-background/40 p-8 text-center space-y-3">
            <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary mx-auto ring-1 ring-primary/20">
              <ShieldCheck className="size-6 text-primary" />
            </div>
            <div className="space-y-1">
              <h4 className="text-sm font-semibold text-foreground">
                Security Audit Ready for {activeBatch?.name || 'Selected Dataset'}
              </h4>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Perform automated timeline continuity verification, intra-clip tamper detection, and cryptographic integrity analysis on this CCTV dataset.
              </p>
            </div>
            <Button
              onClick={() => scanMutation.mutate()}
              disabled={isScanning || isIngesting || !directoryPath}
              className="h-9 gap-1.5 bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90"
            >
              <FileCheck2 className="size-4" />
              <span>Run Security Audit Now</span>
            </Button>
          </div>
        )}

        {/* Audit Results View */}
        {report && !isScanning && (
          <div className="space-y-5">
            {/* Security Verdict Banner */}
            <div
              className={cn(
                'rounded-lg border p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3',
                report.total_gaps_detected > 0
                  ? 'border-destructive/40 bg-destructive/10 text-destructive'
                  : 'border-success/40 bg-success/10 text-success'
              )}
            >
              <div className="flex items-center gap-3">
                {report.total_gaps_detected > 0 ? (
                  <ShieldAlert className="size-6 shrink-0 text-destructive" />
                ) : (
                  <ShieldCheck className="size-6 shrink-0 text-success" />
                )}
                <div>
                  <h4 className="text-sm font-bold tracking-tight">
                    {report.total_gaps_detected > 0
                      ? `SECURITY AUDIT: ${report.total_gaps_detected} Timeline Gap(s) Detected (${report.formatted_total_missing} missing)`
                      : 'CHAIN-OF-CUSTODY VERIFIED: 100% Continuous Footage'}
                  </h4>
                  <p className="text-xs opacity-90 mt-0.5">
                    {report.total_gaps_detected > 0
                      ? 'Discontinuity detected in CCTV recording stream. Possible camera outage, blackout, or missing recording interval.'
                      : 'Zero missing frames or time gaps found. All recording blocks form an unbroken temporal chain.'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Badge
                  className={cn(
                    'font-mono uppercase text-xs px-2.5 py-1',
                    report.total_gaps_detected > 0
                      ? 'bg-destructive text-destructive-foreground'
                      : 'bg-success text-success-foreground'
                  )}
                >
                  {report.security_verdict.replace(/_/g, ' ')}
                </Badge>
              </div>
            </div>

            {/* Metric KPI Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-1">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <Clock className="size-3 text-primary" />
                  Recorded Footage
                </p>
                <p className="text-lg font-bold font-mono text-foreground">{report.formatted_total_footage}</p>
                <p className="text-[10px] text-muted-foreground">{report.total_files_scanned} video files scanned</p>
              </div>

              <div className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-1">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <AlertTriangle className="size-3 text-warning" />
                  Missing Gap Time
                </p>
                <p className={cn('text-lg font-bold font-mono', report.total_gaps_detected > 0 ? 'text-destructive' : 'text-success')}>
                  {report.formatted_total_missing}
                </p>
                <p className="text-[10px] text-muted-foreground">{report.total_gaps_detected} missing interval(s)</p>
              </div>

              <div className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-1">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="size-3 text-success" />
                  Continuity Rating
                </p>
                <p className="text-lg font-bold font-mono text-foreground">{report.overall_continuity_percentage.toFixed(1)}%</p>
                <p className="text-[10px] text-muted-foreground">Temporal coverage integrity</p>
              </div>

              <div className="rounded-lg border border-border/50 bg-card/60 p-3.5 space-y-1">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground flex items-center gap-1.5">
                  <Video className="size-3 text-primary" />
                  Active Cameras
                </p>
                <p className="text-lg font-bold font-mono text-foreground">{report.total_cameras}</p>
                <p className="text-[10px] text-muted-foreground">{report.total_abnormal_trims} suspicious trims</p>
              </div>
            </div>

            {/* Camera Continuity Breakdown */}
            <div className="rounded-lg border border-border/50 bg-card/40 p-4 space-y-3">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Camera Continuity Status
              </h5>
              <div className={cn(
                "grid gap-3",
                report.cameras_summary.length === 1 ? "grid-cols-1" : "grid-cols-1 md:grid-cols-2 lg:grid-cols-3"
              )}>
                {report.cameras_summary.map((cam) => (
                  <div
                    key={cam.camera_id}
                    className="rounded-md border border-border/40 bg-background/40 p-4 space-y-3 text-xs w-full"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-2 text-sm">
                        <Video className="size-4 text-primary" />
                        {cam.camera_id}
                      </span>
                      <Badge
                        variant="outline"
                        className={cn(
                          'font-mono text-[10px] px-2 py-0.5',
                          cam.gap_count > 0 ? 'text-destructive border-destructive/30 bg-destructive/10' : 'text-success border-success/30 bg-success/10'
                        )}
                      >
                        {cam.tamper_verdict.replace(/_/g, ' ')}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-[11px] bg-card/40 p-2.5 rounded border border-border/30">
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Recorded Footage</span>
                        <span className="text-foreground font-bold text-xs">{cam.formatted_footage_duration}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Timeline Span</span>
                        <span className="text-foreground font-bold text-xs">{cam.formatted_span_duration}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Missing Gap Time</span>
                        <span className={cn("font-bold text-xs", cam.gap_count > 0 ? 'text-destructive' : 'text-success')}>
                          {cam.formatted_gap_duration}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px] uppercase font-semibold">Continuity Rating</span>
                        <span className={cn("font-bold text-xs", cam.gap_count > 0 ? 'text-amber-400' : 'text-success')}>
                          {cam.continuity_percentage.toFixed(1)}%
                        </span>
                      </div>
                    </div>

                    {/* Full-Width Continuity Bar */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[10px] font-mono text-muted-foreground">
                        <span>Timeline Coverage Integrity</span>
                        <span className="font-semibold text-foreground">{cam.continuity_percentage.toFixed(1)}%</span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-muted/60 overflow-hidden border border-border/40">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all duration-300',
                            cam.gap_count > 0 ? 'bg-gradient-to-r from-destructive to-amber-500' : 'bg-success'
                          )}
                          style={{ width: `${Math.min(100, Math.max(2, cam.continuity_percentage))}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Detected Missing Gaps List */}
            {report.gaps.length > 0 && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h5 className="text-xs font-semibold uppercase tracking-wider text-destructive flex items-center gap-1.5">
                    <AlertTriangle className="size-3.5" />
                    Missing Footage Intervals (Inter-Clip & Intra-Clip Tamper Audit)
                  </h5>
                  <Badge variant="destructive" className="font-mono text-[10px]">
                    {report.gaps.length} Interval(s) Detected
                  </Badge>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/60 text-muted-foreground text-[10px] uppercase">
                        <th className="py-2 pr-2">Classification</th>
                        <th className="py-2 px-2">Camera</th>
                        <th className="py-2 px-2">Missing From</th>
                        <th className="py-2 px-2">Missing To</th>
                        <th className="py-2 px-2">Duration</th>
                        <th className="py-2 px-2">Tamper Risk</th>
                        <th className="py-2 pl-2">Investigation Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {report.gaps.map((g, idx) => {
                        const isInternalCut = g.severity === 'INTERNAL_TAMPER_CUT';
                        return (
                          <tr key={idx} className={cn("hover:bg-muted/20", isInternalCut && "bg-destructive/10")}>
                            <td className="py-2.5 pr-2">
                              {isInternalCut ? (
                                <Badge className="bg-destructive text-destructive-foreground text-[10px] font-mono uppercase tracking-wide">
                                  ⚡ INTRA-CLIP CUT
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="text-muted-foreground border-border text-[10px] font-mono uppercase">
                                  INTER-CLIP GAP
                                </Badge>
                              )}
                            </td>
                            <td className="py-2.5 px-2 font-semibold text-foreground">{g.camera_id}</td>
                            <td className="py-2.5 px-2 text-destructive font-semibold">{g.gap_start.replace('T', ' ')}</td>
                            <td className="py-2.5 px-2 text-destructive font-semibold">{g.gap_end.replace('T', ' ')}</td>
                            <td className="py-2.5 px-2 font-bold text-destructive">{g.formatted_duration}</td>
                            <td className="py-2.5 px-2">
                              <Badge
                                className={cn(
                                  'text-[10px] uppercase font-mono',
                                  g.tamper_risk === 'HIGH'
                                    ? 'bg-destructive text-destructive-foreground'
                                    : 'bg-warning text-warning-foreground'
                                )}
                              >
                                {g.tamper_risk}
                              </Badge>
                            </td>
                            <td className="py-2.5 pl-2 text-muted-foreground text-[11px] max-w-sm">
                              <div>{g.description}</div>
                              {isInternalCut ? (
                                <div className="text-[10px] text-destructive/90 mt-1 flex items-center gap-1 font-mono">
                                  <span className="font-semibold uppercase tracking-wider text-[9px]">Target Clip:</span>
                                  <span className="truncate max-w-[220px]" title={g.preceding_file}>{g.preceding_file}</span>
                                </div>
                              ) : (
                                g.preceding_file && g.succeeding_file && (
                                  <div className="text-[10px] text-foreground/80 mt-1 flex items-center gap-1 font-mono">
                                    <span className="truncate max-w-[150px]" title={g.preceding_file}>{g.preceding_file}</span>
                                    <span>&rarr;</span>
                                    <span className="truncate max-w-[150px]" title={g.succeeding_file}>{g.succeeding_file}</span>
                                  </div>
                                )
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Chain of Custody Cryptographic Manifest Toggle */}
            <div className="pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowManifest(!showManifest)}
                className="text-xs text-muted-foreground hover:text-foreground gap-1.5 font-mono"
              >
                <Hash className="size-3.5" />
                <span>{showManifest ? 'Hide' : 'View'} Cryptographic Chain-of-Custody Manifest ({report.clips.length} Files)</span>
              </Button>

              {showManifest && (
                <div className="mt-3 rounded-lg border border-border/50 bg-background/50 p-4 max-h-96 overflow-y-auto space-y-2">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/50 text-muted-foreground text-[10px] uppercase">
                        <th className="py-1.5 pr-2">File Name</th>
                        <th className="py-1.5 px-2">Integrity Status</th>
                        <th className="py-1.5 px-2">Camera</th>
                        <th className="py-1.5 px-2">Time Window</th>
                        <th className="py-1.5 px-2">Duration</th>
                        <th className="py-1.5 pl-2">SHA-256 Checksum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                      {report.clips.map((clip, idx) => (
                        <tr key={idx} className={cn("hover:bg-muted/30", clip.has_internal_cut && "bg-destructive/10")}>
                          <td className="py-2 pr-2 font-medium text-foreground max-w-sm" title={clip.file_name}>
                            <div className="truncate font-semibold text-xs">{clip.file_name}</div>
                            {clip.has_internal_cut && (
                              <div className="flex flex-wrap gap-1 mt-1 text-[9px] font-mono">
                                {clip.internal_cut_frame && (
                                  <span className="rounded bg-destructive/20 text-destructive border border-destructive/30 px-1 py-0.5">
                                    Cut Frame #{clip.internal_cut_frame}
                                  </span>
                                )}
                                {clip.gop_cadence_anomaly && (
                                  <span className="rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 px-1 py-0.5" title={clip.gop_cadence_details || "Broken GOP rhythm"}>
                                    Broken GOP
                                  </span>
                                )}
                                {clip.sensor_noise_decorrelation && (
                                  <span className="rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 px-1 py-0.5" title="PRNU sensor noise decorrelated">
                                    PRNU Decorrelation
                                  </span>
                                )}
                                {clip.packet_discontinuity_timestamp && (
                                  <span className="rounded bg-blue-500/20 text-blue-300 border border-blue-500/30 px-1 py-0.5">
                                    PTS Collision {clip.packet_discontinuity_timestamp.toFixed(1)}s
                                  </span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="py-2 px-2">
                            {clip.has_internal_cut ? (
                              <Badge variant="destructive" className="font-mono text-[9px] uppercase">
                                ⚠️ {clip.internal_cut_duration_seconds ? `${Math.round(clip.internal_cut_duration_seconds)}s Missing` : 'Cut Detected'}
                              </Badge>
                            ) : clip.is_abnormally_short ? (
                              <Badge variant="outline" className="text-warning border-warning/30 font-mono text-[9px] uppercase">
                                Trimmed
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-success border-success/30 font-mono text-[9px] uppercase">
                                ✅ Continuous
                              </Badge>
                            )}
                          </td>
                          <td className="py-2 px-2 text-muted-foreground">{clip.camera_id}</td>
                          <td className="py-2 px-2 text-muted-foreground text-[11px]">
                            {clip.start_time.slice(11, 19)} &rarr; {clip.end_time.slice(11, 19)}
                          </td>
                          <td className="py-2 px-2 text-muted-foreground text-[11px]">
                            {Math.floor(clip.duration_seconds / 60)}m {Math.round(clip.duration_seconds % 60)}s
                            {clip.nominal_duration_seconds && Math.round(clip.nominal_duration_seconds) !== Math.round(clip.duration_seconds) ? (
                              <span className="text-destructive block text-[10px]">
                                (Nominal: {Math.floor(clip.nominal_duration_seconds / 60)}m)
                              </span>
                            ) : null}
                          </td>
                          <td className="py-2 pl-2 text-primary font-mono text-[10px] truncate max-w-[140px]" title={clip.sha256_hash}>
                            {clip.sha256_hash.slice(0, 16)}...
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
