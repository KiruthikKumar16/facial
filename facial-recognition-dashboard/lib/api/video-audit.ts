import { authFetch, handleResponse } from './config';

export interface TimelineGap {
  camera_id: string;
  gap_start: string;
  gap_end: string;
  gap_duration_seconds: number;
  formatted_duration: string;
  preceding_file: string;
  succeeding_file: string;
  severity: string;
  tamper_risk: 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
}

export interface CameraContinuitySummary {
  camera_id: string;
  total_clips: number;
  total_footage_seconds: number;
  formatted_footage_duration: string;
  earliest_timestamp: string;
  latest_timestamp: string;
  timeline_span_seconds: number;
  formatted_span_duration: string;
  total_gap_seconds: number;
  formatted_gap_duration: string;
  gap_count: number;
  continuity_percentage: number;
  tamper_verdict: string;
}

export interface VideoClipMetadata {
  file_path: string;
  file_name: string;
  camera_id: string;
  file_size_bytes: number;
  sha256_hash: string;
  width: number;
  height: number;
  fps: number;
  frame_count: number;
  duration_seconds: number;
  start_time: string;
  end_time: string;
  is_abnormally_short: boolean;
  notes: string;
  nominal_duration_seconds?: number | null;
  duration_discrepancy_seconds?: number | null;
  has_internal_cut?: boolean;
  internal_cut_frame?: number | null;
  internal_cut_elapsed_seconds?: number | null;
  internal_cut_start_time?: string | null;
  internal_cut_end_time?: string | null;
  internal_cut_duration_seconds?: number | null;
  packet_discontinuity_timestamp?: number | null;
  sensor_noise_decorrelation?: boolean | null;
  has_freeze_tamper?: boolean | null;
  gop_cadence_anomaly?: boolean | null;
  gop_cadence_details?: string | null;
  enf_phase_anomaly?: boolean | null;
  enf_details?: string | null;
}

export interface VideoAuditReport {
  scan_timestamp: string;
  root_directory: string;
  total_files_scanned: number;
  total_cameras: number;
  overall_continuity_percentage: number;
  security_verdict: string;
  total_footage_duration_seconds: number;
  formatted_total_footage: string;
  total_missing_gap_seconds: number;
  formatted_total_missing: string;
  total_gaps_detected: number;
  total_abnormal_trims: number;
  cameras_summary: CameraContinuitySummary[];
  gaps: TimelineGap[];
  clips: VideoClipMetadata[];
}

export interface IngestionProgress {
  running: boolean;
  completed: boolean;
  error?: string | null;
  directory: string;
  current_file: string;
  current_camera: string;
  file_index: number;
  total_files: number;
  frames_processed: number;
  total_estimated_frames: number;
  faces_detected: number;
  alerts_triggered: number;
  static_frames_skipped?: number;
  active_workers?: number;
  motion_gating_enabled?: boolean;
  vram_free_mb?: number;
  vram_live_reserve_mb?: number;
  sample_fps?: number;
  device?: string;
  cpu_cores?: number;
  progress_percent: number;
  processing_fps: number;
  elapsed_seconds: number;
  eta_seconds: number;
}

export interface GpuStatusResponse {
  device?: string;
  gpu_name?: string;
  cpu_cores?: number;
  vram_info: {
    total_mb: number;
    free_mb: number;
    used_mb: number;
    source: string;
  };
  safe_workers_recommended: number;
  live_reserve_mb: number;
  autoscaler_meta: Record<string, any>;
}

export async function scanCctvFootage(payload: {
  directory: string;
  tolerance_seconds?: number;
  compute_hashes?: boolean;
}): Promise<VideoAuditReport> {
  const res = await authFetch('/api/video-audit/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      directory: payload.directory,
      tolerance_seconds: payload.tolerance_seconds ?? 5.0,
      compute_hashes: payload.compute_hashes ?? true,
    }),
  });
  return handleResponse<VideoAuditReport>(res);
}

export async function fetchLatestAuditReport(): Promise<VideoAuditReport> {
  const res = await authFetch('/api/video-audit/latest-report');
  return handleResponse<VideoAuditReport>(res);
}

export async function startBatchIngest(payload: {
  directory: string;
  sample_fps?: number;
  threshold?: number;
  use_gpu?: boolean;
  batch_name?: string;
  enable_motion_gating?: boolean;
  max_workers?: number;
}): Promise<{ status: string; directory: string; batch_name?: string }> {
  const res = await authFetch('/api/video-audit/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      directory: payload.directory,
      sample_fps: payload.sample_fps ?? 3.0,
      threshold: payload.threshold ?? 0.60,
      use_gpu: payload.use_gpu ?? false,
      batch_name: payload.batch_name,
      enable_motion_gating: payload.enable_motion_gating ?? true,
      max_workers: payload.max_workers,
    }),
  });
  return handleResponse<{ status: string; directory: string; batch_name?: string }>(res);
}

export async function fetchIngestStatus(): Promise<IngestionProgress> {
  const res = await authFetch('/api/video-audit/status');
  return handleResponse<IngestionProgress>(res);
}

export async function fetchGpuStatus(): Promise<GpuStatusResponse> {
  const res = await authFetch('/api/video-audit/gpu-status');
  return handleResponse<GpuStatusResponse>(res);
}

export async function stopBatchIngest(): Promise<{ status: string }> {
  const res = await authFetch('/api/video-audit/stop', {
    method: 'POST',
  });
  return handleResponse<{ status: string }>(res);
}

import { ImportBatch } from '@/lib/types';
import { ImportBatchSchema } from '@/lib/schemas';

export async function fetchImportBatches(): Promise<ImportBatch[]> {
  const res = await authFetch('/api/video-audit/batches');
  const raw = await handleResponse<any>(res);
  try {
    const arr = Array.isArray(raw) ? raw : [];
    return arr
      .map((item: unknown) => {
        const parsed = ImportBatchSchema.safeParse(item);
        return parsed.success ? parsed.data : null;
      })
      .filter(Boolean) as ImportBatch[];
  } catch (e) {
    console.error('fetchImportBatches parsing failed:', e);
    return [];
  }
}

export async function purgeImportBatch(batchId: string): Promise<{ status: string; batch_id: string; deleted_detections: number; deleted_alerts: number }> {
  const res = await authFetch(`/api/video-audit/batches/${encodeURIComponent(batchId)}`, {
    method: 'DELETE',
  });
  return handleResponse<{ status: string; batch_id: string; deleted_detections: number; deleted_alerts: number }>(res);
}

export interface DirectoryItem {
  name: string;
  path: string;
  is_dir: boolean;
  has_videos: boolean;
  is_drive?: boolean;
}

export interface BrowseDirectoryResponse {
  current_path: string;
  parent_path: string | null;
  items: DirectoryItem[];
}

export interface LocateFolderResponse {
  name: string;
  found: boolean;
  path: string | null;
  all_matches: string[];
}

export async function browseDirectories(path?: string): Promise<BrowseDirectoryResponse> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : '';
  const res = await authFetch(`/api/video-audit/browse${qs}`);
  return handleResponse<BrowseDirectoryResponse>(res);
}

export async function locateFolder(name: string): Promise<LocateFolderResponse> {
  const res = await authFetch(`/api/video-audit/locate?name=${encodeURIComponent(name)}`);
  return handleResponse<LocateFolderResponse>(res);
}

