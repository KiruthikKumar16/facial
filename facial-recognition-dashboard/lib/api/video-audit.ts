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
  progress_percent: number;
  processing_fps: number;
  elapsed_seconds: number;
  eta_seconds: number;
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
}): Promise<{ status: string; directory: string }> {
  const res = await authFetch('/api/video-audit/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      directory: payload.directory,
      sample_fps: payload.sample_fps ?? 3.0,
      threshold: payload.threshold ?? 0.60,
      use_gpu: payload.use_gpu ?? false,
    }),
  });
  return handleResponse<{ status: string; directory: string }>(res);
}

export async function fetchIngestStatus(): Promise<IngestionProgress> {
  const res = await authFetch('/api/video-audit/status');
  return handleResponse<IngestionProgress>(res);
}

export async function stopBatchIngest(): Promise<{ status: string }> {
  const res = await authFetch('/api/video-audit/stop', {
    method: 'POST',
  });
  return handleResponse<{ status: string }>(res);
}
