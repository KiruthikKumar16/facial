import type { ProfileRole } from '../types';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:1223'

export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:1223'

export function apiUrl(path: string): string {
  if (path.startsWith('http')) return path
  const base = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL
  const uri = path.startsWith('/') ? path : `/${path}`
  return `${base}${uri}`
}

export async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401 && typeof window !== 'undefined' && window.location.pathname !== '/login') {
    console.error("401 detected, redirecting to login...");
    window.location.assign('/login')
    // Wait a bit to prevent further execution while navigating
    await new Promise(r => setTimeout(r, 1000));
    throw new Error('Unauthorized')
  }
  
  if (!res.ok) {
    let msg = res.statusText
    try {
      const err = await res.json()
      if (err.detail) msg = err.detail
    } catch {
      // Ignore JSON parse errors for non-JSON responses
    }
    throw new Error(`API Error ${res.status}: ${msg}`)
  }
  return res.json()
}

export async function authFetch(path: string, options?: RequestInit): Promise<Response> {
  const token = typeof window !== 'undefined' ? localStorage.getItem('sentinel_token') : null
  const headers = new Headers(options?.headers || {})
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return fetch(apiUrl(path), { ...options, headers })
}

const VALID_ROLES: ProfileRole[] = [
  'employee',
  'vip',
  'visitor',
  'blacklist',
  'watchlist',
]

export const AVATAR_TONES = [
  'sky',
  'amber',
  'rose',
  'violet',
  'emerald',
  'cyan',
  'orange',
  'indigo',
]

export const fetchNodeHealth = async (): Promise<NodeHealthReport[]> => {
  const response = await authFetch('/api/nodes/health')
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.nodes ?? []
    return arr
      .map((item: unknown) => {
        try {
          return {
            nodeId: strOrEmpty(item.node_id ?? item.nodeId),
            hostname: strOrEmpty(item.hostname) || undefined,
            status: strOrEmpty(item.status),
            cpuPercent: numOrZero(item.cpu_percent ?? item.cpuPercent),
            gpuPercent: numOrZero(item.gpu_percent ?? item.gpuPercent),
            memoryPercent: numOrZero(item.memory_percent ?? item.memoryPercent),
            temperatureC: numOrZero(item.temperature_c ?? item.temperatureC) || undefined,
            diskUsagePercent: numOrZero(item.disk_usage_percent ?? item.diskUsagePercent),
            diskFreeMb: numOrZero(item.disk_free_mb ?? item.diskFreeMb),
            cameraFps: numOrZero(item.camera_fps ?? item.cameraFps),
            inferenceFps: numOrZero(item.inference_fps ?? item.inferenceFps),
            networkLatencyMs: numOrZero(item.network_latency_ms ?? item.networkLatencyMs),
            syncQueueLength: numOrZero(item.sync_queue_length ?? item.syncQueueLength),
            eventBacklog: numOrZero(item.event_backlog ?? item.eventBacklog),
            recognitionLatencyMs: numOrZero(item.recognition_latency_ms ?? item.recognitionLatencyMs),
            runtimeMode: strOrEmpty(item.runtime_mode ?? item.runtimeMode),
            frameSamplingRate: numOrZero(item.frame_sampling_rate ?? item.frameSamplingRate),
            syncBatchSize: numOrZero(item.sync_batch_size ?? item.syncBatchSize),
            syncIntervalSeconds: numOrZero(item.sync_interval_seconds ?? item.syncIntervalSeconds),
            reportedAt: strOrEmpty(item.reported_at ?? item.reportedAt),
          }
        } catch (e) {
          console.error('adaptNodeHealth failed:', e)
          return null
        }
      })
      .filter(Boolean) as NodeHealthReport[]
  } catch (e) {
    console.error('fetchNodeHealth adapter failed:', e)
    return []
  }
}

export const fetchVersionBundle = async (): Promise<VersionBundle> => {
  const response = await authFetch('/api/system/version-bundle')
  const raw = await handleResponse<unknown>(response)
  try {
    return {
      detectionModelVersion: strOrEmpty(raw.detection_model_version ?? raw.detectionModelVersion),
      embeddingModelVersion: strOrEmpty(raw.embedding_model_version ?? raw.embeddingModelVersion),
      galleryVersion: numOrZero(raw.gallery_version ?? raw.galleryVersion),
      thresholdVersion: numOrZero(raw.threshold_version ?? raw.thresholdVersion),
      cameraConfigVersion: numOrZero(raw.camera_config_version ?? raw.cameraConfigVersion),
      algorithmVersion: strOrEmpty(raw.algorithm_version ?? raw.algorithmVersion),
      versionBundleHash: strOrEmpty(raw.version_bundle_hash ?? raw.versionBundleHash),
      isProductionReady: boolOrFalse(raw.is_production_ready ?? raw.isProductionReady),
      createdAt: strOrEmpty(raw.created_at ?? raw.createdAt),
    }
  } catch (e) {
    console.error('fetchVersionBundle adapt failed:', e)
    throw e
  }
}

export function getCameraStreamUrl(cameraId: string): string {
  return apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/stream`)
}

export function getCameraSnapshotUrl(cameraId: string): string {
  return apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/stream/snapshot`)
}

export function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

export function isValidProfileRole(v: unknown): v is ProfileRole {
  return typeof v === 'string' && VALID_ROLES.includes(v as ProfileRole)
}

export function normalizeRole(raw: unknown, fallback: ProfileRole = 'visitor'): ProfileRole {
  if (isValidProfileRole(raw)) return raw
  if (raw === 'unknown') return fallback
  return fallback
}

export function strOrEmpty(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

export function numOrZero(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function boolOrFalse(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

export function scaleToPercent(v: unknown): number {
  const n = numOrZero(v)
  return Math.round(n * 100)
}

