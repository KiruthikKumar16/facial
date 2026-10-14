'use client';

import { useState, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  scanCctvFootage,
  fetchLatestAuditReport,
  startBatchIngest,
  fetchIngestStatus,
  stopBatchIngest,
  type VideoAuditReport,
  type IngestionProgress,
} from '@/lib/api';
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
} from 'lucide-react';

export function CctvAuditPanel() {
  const queryClient = useQueryClient();
  const [directoryPath, setDirectoryPath] = useState<string>('D:\\footage');
  const [sampleFps, setSampleFps] = useState<number>(3.0);
  const [tolerance, setTolerance] = useState<number>(5.0);
  const [showManifest, setShowManifest] = useState<boolean>(false);

  // Poll for ingestion status every 1.5 seconds if running
  const { data: ingestStatus, refetch: refetchStatus } = useQuery<IngestionProgress>({
    queryKey: ['video-ingest-status'],
    queryFn: fetchIngestStatus,
    refetchInterval: (query) => {
      return query.state.data?.running ? 1500 : 5000;
    },
  });

  // Cached audit report
  const { data: auditReport, refetch: refetchReport, isLoading: isReportLoading } = useQuery<VideoAuditReport>({
    queryKey: ['video-audit-latest'],
    queryFn: fetchLatestAuditReport,
    retry: false,
  });

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
      }),
    onSuccess: () => {
      refetchStatus();
    },
  });

  // Stop mutation
  const stopMutation = useMutation({
    mutationFn: stopBatchIngest,
    onSuccess: () => {
      refetchStatus();
    },
  });

  const isScanning = scanMutation.isPending;
  const isIngesting = ingestStatus?.running ?? false;
  const report = scanMutation.data || auditReport;

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
      </CardHeader>

      <CardContent className="p-6 space-y-6">
        {/* Controls Bar */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_auto] gap-4 items-end rounded-lg border border-border/50 bg-background/50 p-4">
          <div className="space-y-1.5">
            <Label htmlFor="cctv-dir" className="text-xs font-medium text-foreground flex items-center gap-1.5">
              <FolderSearch className="size-3.5 text-primary" />
              Hard Disk CCTV Footage Path
            </Label>
            <Input
              id="cctv-dir"
              placeholder="e.g. E:\CCTV_3DAYS or D:\footage"
              value={directoryPath}
              onChange={(e) => setDirectoryPath(e.target.value)}
              className="font-mono text-xs bg-card/60"
              disabled={isScanning || isIngesting}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="space-y-1">
              <Label htmlFor="tolerance-sec" className="text-[11px] text-muted-foreground">
                Gap Tolerance (s)
              </Label>
              <Input
                id="tolerance-sec"
                type="number"
                min="1"
                max="60"
                value={tolerance}
                onChange={(e) => setTolerance(Number(e.target.value))}
                className="w-24 text-xs font-mono h-9 bg-card/60"
                disabled={isScanning || isIngesting}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="sample-fps" className="text-[11px] text-muted-foreground">
                Sampling Rate
              </Label>
              <select
                id="sample-fps"
                value={sampleFps}
                onChange={(e) => setSampleFps(Number(e.target.value))}
                className="h-9 rounded-md border border-input bg-card/60 px-3 py-1 text-xs font-mono text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                disabled={isScanning || isIngesting}
              >
                <option value="2.0">2 FPS (Ultra Fast 15x)</option>
                <option value="3.0">3 FPS (Recommended 10x)</option>
                <option value="5.0">5 FPS (Dense 6x)</option>
                <option value="10.0">10 FPS (High Precision)</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              onClick={() => scanMutation.mutate()}
              disabled={isScanning || isIngesting || !directoryPath}
              variant="outline"
              className="h-9 gap-1.5 border-primary/40 hover:bg-primary/10 text-primary font-medium text-xs"
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
                onClick={() => ingestMutation.mutate()}
                disabled={isScanning || isIngesting || !directoryPath}
                className="h-9 gap-1.5 bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90"
              >
                <Play className="size-3.5 fill-current" />
                <span>Ingest Face Recognition</span>
              </Button>
            ) : (
              <Button
                onClick={() => stopMutation.mutate()}
                variant="destructive"
                className="h-9 gap-1.5 font-medium text-xs"
              >
                <Square className="size-3.5 fill-current" />
                <span>Stop Ingest</span>
              </Button>
            )}
          </div>
        </div>

        {/* Scan Error Notice */}
        {scanMutation.isError && (
          <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            <span>Scan Failed: {(scanMutation.error as Error).message}</span>
          </div>
        )}

        {/* Live Ingestion Progress Bar */}
        {isIngesting && ingestStatus && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-3 animate-pulse-subtle">
            <div className="flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <span className="relative flex size-2.5">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex size-2.5 rounded-full bg-primary" />
                </span>
                <span className="font-semibold text-foreground">
                  Ingesting: {ingestStatus.current_file}
                </span>
                <Badge variant="outline" className="font-mono text-[10px]">
                  Cam: {ingestStatus.current_camera}
                </Badge>
              </div>
              <span className="font-mono font-semibold text-primary">
                {ingestStatus.progress_percent.toFixed(1)}% ({ingestStatus.file_index}/{ingestStatus.total_files} files)
              </span>
            </div>

            {/* Progress Track */}
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted shadow-inner">
              <div
                className="h-full rounded-full bg-primary transition-all duration-300 ease-out"
                style={{ width: `${Math.min(100, ingestStatus.progress_percent)}%` }}
              />
            </div>

            {/* Ingestion Stats */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-center font-mono text-[11px] pt-1 border-t border-border/40">
              <div>
                <p className="text-muted-foreground text-[10px] uppercase">Frames</p>
                <p className="font-semibold text-foreground">{ingestStatus.frames_processed.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] uppercase">Speed</p>
                <p className="font-semibold text-foreground">{ingestStatus.processing_fps.toFixed(1)} FPS</p>
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] uppercase">Faces Found</p>
                <p className="font-semibold text-success">{ingestStatus.faces_detected.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] uppercase">Alerts</p>
                <p className="font-semibold text-destructive">{ingestStatus.alerts_triggered}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-[10px] uppercase">ETA</p>
                <p className="font-semibold text-foreground">
                  {ingestStatus.eta_seconds > 60
                    ? `${Math.round(ingestStatus.eta_seconds / 60)}m`
                    : `${Math.round(ingestStatus.eta_seconds)}s`}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Audit Results View */}
        {report && (
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
                  <ShieldAlert className="size-6 shrink-0" />
                ) : (
                  <ShieldCheck className="size-6 shrink-0" />
                )}
                <div>
                  <h4 className="text-sm font-bold tracking-tight">
                    {report.total_gaps_detected > 0
                      ? `SECURITY ALERT: ${report.total_gaps_detected} Footage Gap(s) Detected (${report.formatted_total_missing} missing)`
                      : 'CHAIN-OF-CUSTODY VERIFIED: 100% Continuous Footage'}
                  </h4>
                  <p className="text-xs opacity-90 mt-0.5">
                    {report.total_gaps_detected > 0
                      ? 'Discontinuity detected in CCTV recording stream. Possible camera outage, blackout, or manual clip deletion.'
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {report.cameras_summary.map((cam) => (
                  <div
                    key={cam.camera_id}
                    className="rounded-md border border-border/40 bg-background/40 p-3 space-y-2 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground flex items-center gap-1.5">
                        <Video className="size-3.5 text-primary" />
                        {cam.camera_id}
                      </span>
                      <Badge
                        variant="outline"
                        className={cn(
                          'font-mono text-[10px]',
                          cam.gap_count > 0 ? 'text-destructive border-destructive/30' : 'text-success border-success/30'
                        )}
                      >
                        {cam.tamper_verdict}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Footage</span>
                        <span className="text-foreground">{cam.formatted_footage_duration}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Timeline Span</span>
                        <span className="text-foreground">{cam.formatted_span_duration}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground block text-[10px]">Missing</span>
                        <span className={cam.gap_count > 0 ? 'text-destructive' : 'text-success'}>
                          {cam.formatted_gap_duration}
                        </span>
                      </div>
                    </div>

                    {/* Mini Continuity Bar */}
                    <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                      <div
                        className={cn(
                          'h-full rounded-full transition-all duration-300',
                          cam.gap_count > 0 ? 'bg-destructive' : 'bg-success'
                        )}
                        style={{ width: `${Math.min(100, cam.continuity_percentage)}%` }}
                      />
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
                    Missing Footage Intervals (Suspected Tamper / Trim)
                  </h5>
                  <Badge variant="destructive" className="font-mono text-[10px]">
                    {report.gaps.length} Gap(s) Detected
                  </Badge>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/60 text-muted-foreground text-[10px] uppercase">
                        <th className="py-2 pr-3">Camera</th>
                        <th className="py-2 px-3">Gap Start</th>
                        <th className="py-2 px-3">Gap End</th>
                        <th className="py-2 px-3">Duration</th>
                        <th className="py-2 px-3">Tamper Risk</th>
                        <th className="py-2 pl-3">Preceding & Succeeding Files</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/30">
                      {report.gaps.map((g, idx) => (
                        <tr key={idx} className="hover:bg-muted/20">
                          <td className="py-2.5 pr-3 font-semibold text-foreground">{g.camera_id}</td>
                          <td className="py-2.5 px-3 text-destructive">{g.gap_start.replace('T', ' ')}</td>
                          <td className="py-2.5 px-3 text-destructive">{g.gap_end.replace('T', ' ')}</td>
                          <td className="py-2.5 px-3 font-bold text-destructive">{g.formatted_duration}</td>
                          <td className="py-2.5 px-3">
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
                          <td className="py-2.5 pl-3 text-muted-foreground truncate max-w-xs text-[11px]">
                            {g.preceding_file} &rarr; {g.succeeding_file}
                          </td>
                        </tr>
                      ))}
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
                <div className="mt-3 rounded-lg border border-border/50 bg-background/50 p-4 max-h-72 overflow-y-auto space-y-2">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-border/50 text-muted-foreground text-[10px] uppercase">
                        <th className="py-1.5 pr-2">File Name</th>
                        <th className="py-1.5 px-2">Camera</th>
                        <th className="py-1.5 px-2">Start Time</th>
                        <th className="py-1.5 px-2">Duration</th>
                        <th className="py-1.5 pl-2">SHA-256 Checksum</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                      {report.clips.map((clip, idx) => (
                        <tr key={idx} className="hover:bg-muted/30">
                          <td className="py-1.5 pr-2 truncate max-w-xs text-foreground">{clip.file_name}</td>
                          <td className="py-1.5 px-2 text-muted-foreground">{clip.camera_id}</td>
                          <td className="py-1.5 px-2 text-muted-foreground">{clip.start_time.replace('T', ' ')}</td>
                          <td className="py-1.5 px-2 text-muted-foreground">{Math.round(clip.duration_seconds)}s</td>
                          <td className="py-1.5 pl-2 text-primary font-mono text-[10px] truncate max-w-[140px]" title={clip.sha256_hash}>
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
