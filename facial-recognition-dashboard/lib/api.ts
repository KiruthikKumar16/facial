/**
 * Real API client for facial recognition backend.
 *
 * Supports both local development and cloud deployment:
 * - Local: http://localhost:1223
 * - Render: https://facial-api.render.com
 *
 * Configure via environment variables:
 * NEXT_PUBLIC_API_URL - Base API URL (default: http://localhost:1223)
 * NEXT_PUBLIC_WS_URL - WebSocket URL (default: ws://localhost:1223)
 */

import type {
  Alert,
  AttendanceRecord,
  Camera,
  CameraConfigProfile,
  DemographicSlice,
  DuplicateCandidate,
  FaceLog,
  FootfallBucket,
  ForensicMatch,
  Gender,
  ModelThresholds,
  MovementEdge,
  MovementNetwork,
  NodeHealthReport,
  Profile,
  ProfileRole,
  RecognitionProvenance,
  SubjectTrajectory,
  SystemKpis,
  SystemHealth,
  TrajectoryNode,
  UnknownCapture,
  UnregisteredSubject,
  VersionBundle,
} from './types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:1223'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:1223'
const EDGE_API_URL = process.env.NEXT_PUBLIC_EDGE_API_URL || ''

const VALID_ROLES: ProfileRole[] = [
  'employee',
  'vip',
  'visitor',
  'blacklist',
  'watchlist',
]

const AVATAR_TONES = [
  'sky',
  'amber',
  'rose',
  'violet',
  'emerald',
  'cyan',
  'orange',
  'indigo',
]

function apiUrl(path: string): string {
  return `${API_URL}${path}`
}

function forensicApiUrl(path: string): string {
  const baseUrl = EDGE_API_URL.trim() || API_URL
  return `${baseUrl.replace(/\/$/, '')}${path}`
}

function wsUrl(channel: string): string {
  return `${WS_URL}/ws/${channel}`
}

/**
 * Returns the URL for the MJPEG live stream of a camera's annotated feed.
 * Drop this directly into an <img src=...> element.
 */
export function getCameraStreamUrl(cameraId: string): string {
  return apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/stream`)
}

/**
 * Returns the URL for a single JPEG snapshot of the latest annotated frame.
 */
export function getCameraSnapshotUrl(cameraId: string): string {
  return apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/stream/snapshot`)
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `API Error: ${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (typeof body?.detail === 'string') message = body.detail
      else if (Array.isArray(body?.detail)) {
        message = body.detail
          .map((item: any) => item?.msg ?? JSON.stringify(item))
          .join(', ')
      }
    } catch {
      // Keep the status-text fallback when the backend did not return JSON.
    }
    throw new Error(message)
  }
  return response.json()
}

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

function isValidProfileRole(v: unknown): v is ProfileRole {
  return typeof v === 'string' && VALID_ROLES.includes(v as ProfileRole)
}

function normalizeRole(raw: unknown, fallback: ProfileRole = 'visitor'): ProfileRole {
  if (isValidProfileRole(raw)) return raw
  if (raw === 'unknown') return fallback
  return fallback
}

function strOrEmpty(v: unknown): string {
  if (v === null || v === undefined) return ''
  return String(v)
}

function numOrZero(v: unknown): number {
  if (v === null || v === undefined) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function boolOrFalse(v: unknown): boolean {
  return v === true || v === 'true' || v === 1 || v === '1'
}

function scaleToPercent(v: unknown): number {
  const n = numOrZero(v)
  return Math.round(n * 100)
}

// ==================== Adapter Functions ====================

export function adaptCamera(raw: any): Camera {
  return {
    id: strOrEmpty(raw.id),
    name: strOrEmpty(raw.name),
    zone: strOrEmpty(raw.zone),
    ipAddress: strOrEmpty(raw.ip_address ?? raw.ipAddress),
    rtspUrl: strOrEmpty(raw.rtsp_url ?? raw.rtspUrl),
    status: (['online', 'degraded', 'offline'].includes(raw.status)
      ? raw.status
      : 'offline') as Camera['status'],
    pingMs: numOrZero(raw.ping_ms ?? raw.pingMs),
    frameLatencyMs: numOrZero(raw.frame_latency_ms ?? raw.frameLatencyMs),
    fps: numOrZero(raw.fps),
    gpuLoad: numOrZero(raw.gpu_load ?? raw.gpuLoad),
    cpuLoad: numOrZero(raw.cpu_load ?? raw.cpuLoad),
    lastHeartbeat: strOrEmpty(raw.last_heartbeat ?? raw.lastHeartbeat),
    detectionsToday: numOrZero(raw.detections_today ?? raw.detectionsToday),
  }
}

export function adaptFaceLog(raw: any): FaceLog {
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
    cameraName: strOrEmpty(raw.camera_name ?? raw.cameraName),
    timestamp: strOrEmpty(raw.timestamp),
    status: (['recognized', 'flagged', 'unknown'].includes(raw.status)
      ? raw.status
      : 'unknown') as FaceLog['status'],
    confidence: raw.confidence !== undefined && raw.confidence !== null
      ? raw.confidence > 1 ? numOrZero(raw.confidence) : scaleToPercent(raw.confidence)
      : 0,
    livenessScore: raw.liveness_score !== undefined && raw.liveness_score !== null
      ? raw.liveness_score > 1 ? numOrZero(raw.liveness_score) : scaleToPercent(raw.liveness_score)
      : raw.livenessScore !== undefined && raw.livenessScore !== null
        ? numOrZero(raw.livenessScore)
        : 0,
    profileId: raw.profile_id ?? raw.profileId ?? null,
    profileName: raw.profile_name ?? raw.profileName ?? null,
    role: raw.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
    age: numOrZero(raw.age),
    gender: (['male', 'female', 'unknown'].includes(raw.gender)
      ? raw.gender
      : 'unknown') as Gender,
    wearingMask: boolOrFalse(raw.wearing_mask ?? raw.wearingMask),
    wearingGlasses: boolOrFalse(raw.wearing_glasses ?? raw.wearingGlasses),
    snapshotTone: strOrEmpty(raw.snapshot_tone ?? raw.snapshotTone) ||
      AVATAR_TONES[hashString(strOrEmpty(raw.id)) % AVATAR_TONES.length],
  }
}

export function adaptAlert(raw: any): Alert {
  return {
    id: strOrEmpty(raw.id),
    logId: strOrEmpty(raw.log_id ?? raw.logId),
    cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
    cameraName: strOrEmpty(raw.camera_name ?? raw.cameraName),
    timestamp: strOrEmpty(raw.timestamp),
    severity: (['critical', 'high', 'medium'].includes(raw.severity)
      ? raw.severity
      : 'medium') as Alert['severity'],
    reason: strOrEmpty(raw.reason),
    profileId: raw.profile_id ?? raw.profileId ?? null,
    profileName: strOrEmpty(raw.profile_name ?? raw.profileName),
    role: normalizeRole(raw.role),
    confidence: raw.confidence !== undefined && raw.confidence !== null
      ? raw.confidence > 1 ? numOrZero(raw.confidence) : scaleToPercent(raw.confidence)
      : 0,
    acknowledged: boolOrFalse(raw.acknowledged),
    snapshotTone: strOrEmpty(raw.snapshot_tone ?? raw.snapshotTone) ||
      AVATAR_TONES[hashString(strOrEmpty(raw.id)) % AVATAR_TONES.length],
  }
}

export function adaptUnknownCapture(raw: any): UnknownCapture {
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
    cameraName: strOrEmpty(raw.camera_name ?? raw.cameraName),
    timestamp: strOrEmpty(raw.timestamp),
    confidence: raw.confidence !== undefined && raw.confidence !== null
      ? raw.confidence > 1 ? numOrZero(raw.confidence) : scaleToPercent(raw.confidence)
      : 0,
    livenessScore: raw.liveness_score !== undefined && raw.liveness_score !== null
      ? raw.liveness_score > 1 ? numOrZero(raw.liveness_score) : scaleToPercent(raw.liveness_score)
      : raw.livenessScore !== undefined && raw.livenessScore !== null
        ? numOrZero(raw.livenessScore)
        : 0,
    age: numOrZero(raw.age),
    gender: (['male', 'female', 'unknown'].includes(raw.gender)
      ? raw.gender
      : 'unknown') as Gender,
    snapshotTone: strOrEmpty(raw.snapshot_tone ?? raw.snapshotTone) ||
      AVATAR_TONES[hashString(strOrEmpty(raw.id)) % AVATAR_TONES.length],
  }
}

export function adaptProfile(raw: any): Profile {
  const id = strOrEmpty(raw.id)
  const rawGender = raw.gender
  const gender: Gender = ['male', 'female', 'unknown'].includes(rawGender)
    ? rawGender
    : 'unknown'

  return {
    id,
    name: strOrEmpty(raw.name),
    role: normalizeRole(raw.role),
    department: strOrEmpty(raw.department),
    embeddingStatus: (['indexed', 'pending', 'stale', 'missing'].includes(
      raw.embedding_status ?? raw.embeddingStatus,
    )
      ? (raw.embedding_status ?? raw.embeddingStatus)
      : 'pending') as Profile['embeddingStatus'],
    embeddingCount: numOrZero(raw.embedding_count ?? raw.embeddingCount),
    enrolledAt: strOrEmpty(raw.enrolled_at ?? raw.enrolledAt),
    lastSeen: raw.last_seen ?? raw.lastSeen ?? null,
    age: numOrZero(raw.age),
    gender,
    avatarTone: strOrEmpty(raw.avatarTone) ||
      AVATAR_TONES[hashString(id) % AVATAR_TONES.length],
    notes: raw.notes !== undefined && raw.notes !== null && raw.notes !== ''
      ? String(raw.notes)
      : undefined,
  }
}

export function adaptKpis(raw: any): SystemKpis {
  if (raw && typeof raw.connectedCameras === 'number') {
    return {
      connectedCameras: numOrZero(raw.connectedCameras),
      totalCameras: numOrZero(raw.totalCameras ?? raw.connectedCameras),
      detectionsToday: numOrZero(raw.detectionsToday),
      activeAlerts: numOrZero(raw.activeAlerts),
      systemHealth: (['green', 'yellow', 'red'].includes(raw.systemHealth)
        ? raw.systemHealth
        : 'green') as SystemHealth,
      gpuLoad: numOrZero(raw.gpuLoad),
      cpuLoad: numOrZero(raw.cpuLoad),
      avgLatencyMs: numOrZero(raw.avgLatencyMs),
    }
  }

  const camerasOnline = numOrZero(raw?.cameras_online)
  const recognitionsToday = numOrZero(raw?.recognitions_today)
  const unknownsToday = numOrZero(raw?.unknowns_today)
  const criticalAlerts = numOrZero(raw?.critical_alerts)
  const activeAlertsLegacy = numOrZero(raw?.active_alerts)

  return {
    connectedCameras: camerasOnline,
    totalCameras: numOrZero(raw?.cameras_total) || camerasOnline,
    detectionsToday: recognitionsToday + unknownsToday,
    activeAlerts: criticalAlerts || activeAlertsLegacy || 0,
    systemHealth: (['green', 'yellow', 'red'].includes(raw?.systemHealth ?? raw?.system_health)
      ? (raw?.systemHealth ?? raw?.system_health)
      : 'green') as SystemHealth,
    gpuLoad: numOrZero(raw?.gpu_load ?? raw?.gpuLoad),
    cpuLoad: numOrZero(raw?.cpu_load ?? raw?.cpuLoad),
    avgLatencyMs: numOrZero(raw?.avg_latency_ms ?? raw?.avgLatencyMs),
  }
}

export function adaptThresholds(raw: any): ModelThresholds {
  const simConfRaw = raw?.similarity_confidence ?? raw?.recognitionConfidence
  const livenessRaw = raw?.liveness_threshold ?? raw?.livenessScore

  return {
    recognitionConfidence:
      typeof simConfRaw === 'number' && simConfRaw <= 1
        ? Math.round(simConfRaw * 100)
        : numOrZero(simConfRaw) || 60,
    livenessScore:
      typeof livenessRaw === 'number' && livenessRaw <= 1
        ? Math.round(livenessRaw * 100)
        : numOrZero(livenessRaw) || 50,
    unknownFaceRetentionDays: numOrZero(
      raw?.unknownFaceRetentionDays ?? raw?.unknown_face_retention_days,
    ) || 14,
    autoAlertOnBlacklist:
      raw?.autoAlertOnBlacklist !== undefined
        ? boolOrFalse(raw.autoAlertOnBlacklist)
        : raw?.auto_alert_on_blacklist !== undefined
          ? boolOrFalse(raw.auto_alert_on_blacklist)
          : true,
  }
}

export function reverseAdaptThresholds(t: ModelThresholds): any {
  return {
    similarity_confidence: t.recognitionConfidence / 100,
    liveness_threshold: t.livenessScore / 100,
    age_variance: 5.0,
    unknownFaceRetentionDays: t.unknownFaceRetentionDays,
    autoAlertOnBlacklist: t.autoAlertOnBlacklist,
  }
}

function adaptMiniProfile(p: any): Pick<Profile, 'id' | 'name' | 'role' | 'avatarTone'> {
  const id = strOrEmpty(p?.id)
  return {
    id,
    name: strOrEmpty(p?.name),
    role: normalizeRole(p?.role),
    avatarTone: strOrEmpty(p?.avatarTone) ||
      AVATAR_TONES[hashString(id) % AVATAR_TONES.length],
  }
}

export function adaptDuplicateCandidate(raw: any): DuplicateCandidate {
  if (raw.profileAId && !raw.profileA && !raw.profile_a) {
    return {
      id: strOrEmpty(raw.id ?? `${raw.profileAId}:${raw.profileBId}`),
      profileA: {
        id: strOrEmpty(raw.profileAId),
        name: strOrEmpty(raw.profileAName),
        role: normalizeRole(raw.profileARole),
        avatarTone: strOrEmpty(raw.profileAAvatarTone) ||
          AVATAR_TONES[hashString(strOrEmpty(raw.profileAId)) % AVATAR_TONES.length],
      },
      profileB: {
        id: strOrEmpty(raw.profileBId),
        name: strOrEmpty(raw.profileBName),
        role: normalizeRole(raw.profileBRole),
        avatarTone: strOrEmpty(raw.profileBAvatarTone) ||
          AVATAR_TONES[hashString(strOrEmpty(raw.profileBId)) % AVATAR_TONES.length],
      },
      cosineSimilarity: numOrZero(raw.cosine_similarity ?? raw.cosineSimilarity ?? raw.similarity_score),
      sharedSightings: numOrZero(raw.shared_sightings ?? raw.sharedSightings),
    }
  }
  return {
    id: strOrEmpty(raw.id),
    profileA: adaptMiniProfile(raw.profile_a ?? raw.profileA),
    profileB: adaptMiniProfile(raw.profile_b ?? raw.profileB),
    cosineSimilarity: numOrZero(raw.cosine_similarity ?? raw.cosineSimilarity),
    sharedSightings: numOrZero(raw.shared_sightings ?? raw.sharedSightings),
  }
}

export function adaptTrajectoryNode(raw: any): TrajectoryNode {
  return {
    cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
    cameraName: strOrEmpty(raw.camera_name ?? raw.cameraName),
    zone: strOrEmpty(raw.zone),
    timestamp: strOrEmpty(raw.timestamp),
    confidence: raw.confidence !== undefined && raw.confidence !== null
      ? raw.confidence > 1 ? numOrZero(raw.confidence) : scaleToPercent(raw.confidence)
      : 0,
    snapshotTone: strOrEmpty(raw.snapshot_tone ?? raw.snapshotTone) ||
      AVATAR_TONES[hashString(strOrEmpty(raw.camera_id ?? raw.cameraId ?? '')) % AVATAR_TONES.length],
  }
}

export function adaptSubjectTrajectory(raw: any): SubjectTrajectory {
  const pathRaw = raw?.path ?? raw?.nodes ?? []
  const path: TrajectoryNode[] = Array.isArray(pathRaw)
    ? pathRaw.map((n: any) => {
        try {
          return adaptTrajectoryNode(n)
        } catch {
          return null
        }
      }).filter(Boolean) as TrajectoryNode[]
    : []

  return {
    profileId: raw?.profile_id ?? raw?.profileId ?? null,
    profileName: strOrEmpty(raw?.profile_name ?? raw?.profileName),
    role: raw?.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
    path,
  }
}

export function adaptForensicMatch(raw: any): ForensicMatch {
  const profileId = raw?.profile_id ?? raw?.profileId
  return {
    profileId: profileId ?? null,
    profileName: strOrEmpty(raw?.profile_name ?? raw?.profileName),
    role: raw?.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
    cosineSimilarity: numOrZero(
      raw?.cosine_similarity ?? raw?.cosineSimilarity ?? raw?.match_score,
    ),
    lastSeen: strOrEmpty(raw?.last_seen ?? raw?.lastSeen),
    cameraName: strOrEmpty(raw?.camera_name ?? raw?.cameraName),
    avatarTone: strOrEmpty(raw?.avatarTone) ||
      AVATAR_TONES[hashString(strOrEmpty(profileId ?? raw?.profile_name ?? '')) % AVATAR_TONES.length],
  }
}

export function adaptAttendanceRecord(raw: any): AttendanceRecord {
  const profileId = strOrEmpty(raw.profile_id ?? raw.profileId)
  return {
    profileId,
    profileName: strOrEmpty(raw.profile_name ?? raw.profileName),
    role: normalizeRole(raw.role),
    department: strOrEmpty(raw.department),
    checkIn: strOrEmpty(raw.check_in ?? raw.checkIn),
    checkOut: strOrEmpty(raw.check_out ?? raw.checkOut),
    totalSightings: numOrZero(raw.total_sightings ?? raw.totalSightings),
    avatarTone: strOrEmpty(raw.avatarTone) ||
      AVATAR_TONES[hashString(profileId) % AVATAR_TONES.length],
  }
}

export function adaptFootfallBucket(raw: any): FootfallBucket {
  return {
    hour: strOrEmpty(raw.hour ?? raw.bucket ?? raw.label),
    detections: numOrZero(raw.detections ?? raw.total),
    recognized: numOrZero(raw.recognized),
    unknown: numOrZero(raw.unknown),
  }
}

export function adaptDemographicSlice(raw: any): DemographicSlice {
  return {
    label: strOrEmpty(raw.label ?? raw.bracket ?? raw.category),
    value: numOrZero(raw.value ?? raw.count),
  }
}

// ==================== System KPIs ====================

export const fetchKpis = async (): Promise<SystemKpis> => {
  const response = await fetch(apiUrl('/api/kpis'))
  const raw = await handleResponse<any>(response)
  try {
    return adaptKpis(raw)
  } catch (e) {
    console.error('adaptKpis failed:', e)
    return adaptKpis({})
  }
}

// ==================== Cameras ====================

export const fetchCameras = async (): Promise<Camera[]> => {
  const response = await fetch(apiUrl('/api/cameras'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.cameras ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptCamera(item)
        } catch (e) {
          console.error('adaptCamera failed:', e)
          return null
        }
      })
      .filter(Boolean) as Camera[]
  } catch (e) {
    console.error('fetchCameras adapter failed:', e)
    return []
  }
}

// ==================== Detection Logs ====================

export const fetchFaceLogs = async (
  limit: number = 100,
  offset: number = 0,
): Promise<FaceLog[]> => {
  const qs = `?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`
  const response = await fetch(apiUrl(`/api/logs${qs}`))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.logs ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptFaceLog(item)
        } catch (e) {
          console.error('adaptFaceLog failed:', e)
          return null
        }
      })
      .filter(Boolean) as FaceLog[]
  } catch (e) {
    console.error('fetchFaceLogs adapter failed:', e)
    return []
  }
}

// ==================== Alerts ====================

export const fetchAlerts = async (limit: number = 50): Promise<Alert[]> => {
  const qs = `?limit=${encodeURIComponent(String(limit))}`
  const response = await fetch(apiUrl(`/api/alerts${qs}`))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.alerts ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptAlert(item)
        } catch (e) {
          console.error('adaptAlert failed:', e)
          return null
        }
      })
      .filter(Boolean) as Alert[]
  } catch (e) {
    console.error('fetchAlerts adapter failed:', e)
    return []
  }
}

export const acknowledgeAlert = async (
  alertId: string,
  acknowledged: boolean = true,
): Promise<Alert> => {
  const response = await fetch(
    apiUrl(`/api/alerts/${encodeURIComponent(alertId)}/acknowledge`),
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ acknowledged }),
    },
  )
  const raw = await handleResponse<any>(response)
  try {
    return adaptAlert(raw)
  } catch (e) {
    console.error('acknowledgeAlert adapt failed:', e)
    return adaptAlert({ id: alertId, acknowledged })
  }
}

// ==================== Profiles ====================

export const fetchProfiles = async (): Promise<Profile[]> => {
  const response = await fetch(apiUrl('/api/profiles'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.profiles ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptProfile(item)
        } catch (e) {
          console.error('adaptProfile failed:', e)
          return null
        }
      })
      .filter(Boolean) as Profile[]
  } catch (e) {
    console.error('fetchProfiles adapter failed:', e)
    return []
  }
}

export const fetchProfile = async (profileId: string): Promise<Profile | null> => {
  const response = await fetch(
    apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`),
  )
  const raw = await handleResponse<any>(response)
  try {
    return raw ? adaptProfile(raw) : null
  } catch (e) {
    console.error('fetchProfile adapt failed:', e)
    return null
  }
}

export const updateProfile = async (
  profileId: string,
  payload: { name?: string; role?: ProfileRole; department?: string },
): Promise<Profile> => {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return adaptProfile(await handleResponse<any>(response))
}

export const deleteProfile = async (profileId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`), {
    method: 'DELETE',
  })
  if (!response.ok) await handleResponse<any>(response)
}

export const deleteProfileEmbedding = async (
  profileId: string,
  embeddingId: string,
): Promise<void> => {
  const response = await fetch(apiUrl(
    `/api/profiles/${encodeURIComponent(profileId)}/embeddings/${encodeURIComponent(embeddingId)}`,
  ), { method: 'DELETE' })
  if (!response.ok) await handleResponse<any>(response)
}

export const deleteProfileEmbeddings = async (profileId: string): Promise<void> => {
  const response = await fetch(apiUrl(
    `/api/profiles/${encodeURIComponent(profileId)}/embeddings`,
  ), { method: 'DELETE' })
  if (!response.ok) await handleResponse<any>(response)
}

type CreateProfilePayload = {
  name: string
  role?: string
  department?: string
  age?: number
  gender?: string
  notes?: string
  photos?: File[]
}

export const createProfile = async (
  payload: CreateProfilePayload,
): Promise<Profile> => {
  const formData = new FormData()
  formData.append('name', payload.name)
  if (payload.role !== undefined) formData.append('role', payload.role)
  if (payload.department !== undefined)
    formData.append('department', payload.department)
  if (payload.age !== undefined)
    formData.append('age', String(payload.age))
  if (payload.gender !== undefined)
    formData.append('gender', payload.gender)
  if (payload.notes !== undefined && payload.notes !== '')
    formData.append('notes', payload.notes)
  if (payload.photos && payload.photos.length > 0) {
    for (const photo of payload.photos) {
      formData.append('photos', photo)
    }
  }

  const response = await fetch(apiUrl('/api/profiles'), {
    method: 'POST',
    body: formData,
  })
  const raw = await handleResponse<any>(response)
  try {
    return adaptProfile(raw)
  } catch (e) {
    console.error('createProfile adapt failed:', e)
    return adaptProfile({ id: '', name: payload.name })
  }
}

type MergeProfilesResult = {
  merged: true
  keptProfileId: string
  deletedProfileId: string
}

export const mergeProfiles = async (
  profileAId: string,
  profileBId: string,
  keepProfileId?: string,
  deleteMerged: boolean = true,
): Promise<MergeProfilesResult> => {
  const body: any = {
    profileAId,
    profileBId,
    deleteMerged,
  }
  if (keepProfileId !== undefined) {
    body.keepProfile = keepProfileId
    body.keepProfileId = keepProfileId
  }

  const response = await fetch(apiUrl('/api/profiles/merge'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const raw = await handleResponse<any>(response)
  try {
    return {
      merged: true,
      keptProfileId: strOrEmpty(
        raw.keptProfileId ?? raw.kept_profile_id ?? keepProfileId ?? profileAId,
      ),
      deletedProfileId: strOrEmpty(
        raw.deletedProfileId ?? raw.deleted_profile_id ??
          (keepProfileId === profileAId ? profileBId : profileAId),
      ),
    }
  } catch (e) {
    console.error('mergeProfiles adapt failed:', e)
    return {
      merged: true,
      keptProfileId: keepProfileId ?? profileAId,
      deletedProfileId: keepProfileId === profileAId ? profileBId : profileAId,
    }
  }
}

// ==================== Unknown Captures ====================

export const fetchUnknownCaptures = async (): Promise<UnknownCapture[]> => {
  const logs = await fetchFaceLogs(1000)
  try {
    return logs
      .filter((log) => log.status === 'unknown')
      .map((log) => {
        try {
          return adaptUnknownCapture({
            ...log,
            snapshot_tone: log.snapshotTone,
          })
        } catch {
          return null
        }
      })
      .filter(Boolean) as UnknownCapture[]
  } catch (e) {
    console.error('fetchUnknownCaptures adapt failed:', e)
    return []
  }
}

function adaptUnregisteredSubject(raw: any): UnregisteredSubject {
  return {
    id: strOrEmpty(raw.id),
    displayName: strOrEmpty(raw.display_name ?? raw.displayName),
    captureCount: numOrZero(raw.capture_count ?? raw.captureCount),
    firstSeen: strOrEmpty(raw.first_seen ?? raw.firstSeen),
    lastSeen: strOrEmpty(raw.last_seen ?? raw.lastSeen),
    cameras: Array.isArray(raw.cameras) ? raw.cameras.map(String) : [],
    bestConfidence: numOrZero(raw.best_confidence ?? raw.bestConfidence),
    representativeFingerprint: strOrEmpty(raw.representative_fingerprint ?? raw.representativeFingerprint),
    vectorDimension: numOrZero(raw.vector_dimension ?? raw.vectorDimension),
    eventIds: Array.isArray(raw.event_ids ?? raw.eventIds) ? (raw.event_ids ?? raw.eventIds).map(String) : [],
    status: strOrEmpty(raw.status),
  }
}

export const fetchUnregisteredSubjects = async (): Promise<UnregisteredSubject[]> => {
  const response = await fetch(apiUrl('/api/unregistered-subjects'))
  const raw = await handleResponse<any>(response)
  return (Array.isArray(raw) ? raw : []).map(adaptUnregisteredSubject)
}

export const renameUnregisteredSubject = async (id: string, displayName: string) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}`), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ display_name: displayName }) })
  return adaptUnregisteredSubject(await handleResponse<any>(response))
}

export const registerUnregisteredSubject = async (id: string, payload: { name: string; role: ProfileRole; department?: string }) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/register`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  return adaptProfile(await handleResponse<any>(response))
}

export const assignUnregisteredSubject = async (id: string, profileId: string) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/assign`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_id: profileId }) })
  return adaptProfile(await handleResponse<any>(response))
}

export const mergeUnregisteredSubjects = async (id: string, sourceSubjectId: string) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/merge`), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_subject_id: sourceSubjectId }) })
  return adaptUnregisteredSubject(await handleResponse<any>(response))
}

export const deleteUnregisteredEvent = async (subjectId: string, eventId: string) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(subjectId)}/events/${encodeURIComponent(eventId)}`), { method: 'DELETE' })
  if (!response.ok) await handleResponse<any>(response)
}

export const deleteUnregisteredSubject = async (subjectId: string) => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(subjectId)}`), { method: 'DELETE' })
  if (!response.ok) await handleResponse<any>(response)
}

// ==================== Duplicates & Analytics ====================

export const fetchDuplicates = async (): Promise<DuplicateCandidate[]> => {
  const response = await fetch(apiUrl('/api/analytics/duplicates'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.duplicates ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptDuplicateCandidate(item)
        } catch (e) {
          console.error('adaptDuplicateCandidate failed:', e)
          return null
        }
      })
      .filter(Boolean) as DuplicateCandidate[]
  } catch (e) {
    console.error('fetchDuplicates adapter failed:', e)
    return []
  }
}

export const fetchTrajectory = async (
  profileId?: string,
  hours?: number,
): Promise<SubjectTrajectory | null> => {
  const params = new URLSearchParams()
  if (profileId !== undefined)
    params.append('profileId', encodeURIComponent(profileId))
  if (hours !== undefined)
    params.append('hours', encodeURIComponent(String(hours)))
  const qs = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(apiUrl(`/api/analytics/trajectory${qs}`))
  const raw = await handleResponse<any>(response)
  try {
    return raw ? adaptSubjectTrajectory(raw) : null
  } catch (e) {
    console.error('fetchTrajectory adapt failed:', e)
    return null
  }
}

export const fetchMovementNetwork = async (hours = 24): Promise<MovementNetwork> => {
  const response = await fetch(apiUrl(`/api/analytics/movement-network?hours=${hours}`))
  const raw = await handleResponse<any>(response)
  const edges = Array.isArray(raw?.edges) ? raw.edges : []
  return {
    edges: edges.map((edge: any): MovementEdge => ({
      fromCameraId: strOrEmpty(edge.fromCameraId ?? edge.from_camera_id),
      fromCameraName: strOrEmpty(edge.fromCameraName ?? edge.from_camera_name),
      toCameraId: strOrEmpty(edge.toCameraId ?? edge.to_camera_id),
      toCameraName: strOrEmpty(edge.toCameraName ?? edge.to_camera_name),
      count: numOrZero(edge.count),
      lastSeen: strOrEmpty(edge.lastSeen ?? edge.last_seen),
      averageTravelSeconds: numOrZero(edge.averageTravelSeconds ?? edge.average_travel_seconds),
    })),
  }
}

export const fetchFootfall = async (days?: number): Promise<FootfallBucket[]> => {
  const qs =
    days !== undefined
      ? `?days=${encodeURIComponent(String(days))}`
      : ''
  const response = await fetch(apiUrl(`/api/analytics/footfall${qs}`))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.buckets ?? raw?.footfall ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptFootfallBucket(item)
        } catch (e) {
          console.error('adaptFootfallBucket failed:', e)
          return null
        }
      })
      .filter(Boolean) as FootfallBucket[]
  } catch (e) {
    console.error('fetchFootfall adapter failed:', e)
    return []
  }
}

export const fetchAgeDistribution = async (): Promise<DemographicSlice[]> => {
  const response = await fetch(apiUrl('/api/analytics/age-distribution'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.distribution ?? raw?.slices ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptDemographicSlice(item)
        } catch (e) {
          console.error('adaptDemographicSlice failed:', e)
          return null
        }
      })
      .filter(Boolean) as DemographicSlice[]
  } catch (e) {
    console.error('fetchAgeDistribution adapter failed:', e)
    return []
  }
}

export const fetchGenderDistribution = async (): Promise<DemographicSlice[]> => {
  const response = await fetch(apiUrl('/api/analytics/gender-distribution'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.distribution ?? raw?.slices ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptDemographicSlice(item)
        } catch (e) {
          console.error('adaptDemographicSlice failed:', e)
          return null
        }
      })
      .filter(Boolean) as DemographicSlice[]
  } catch (e) {
    console.error('fetchGenderDistribution adapter failed:', e)
    return []
  }
}

export const fetchAttendance = async (days?: number): Promise<AttendanceRecord[]> => {
  const qs =
    days !== undefined
      ? `?days=${encodeURIComponent(String(days))}`
      : ''
  const response = await fetch(apiUrl(`/api/analytics/attendance${qs}`))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.records ?? raw?.attendance ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptAttendanceRecord(item)
        } catch (e) {
          console.error('adaptAttendanceRecord failed:', e)
          return null
        }
      })
      .filter(Boolean) as AttendanceRecord[]
  } catch (e) {
    console.error('fetchAttendance adapter failed:', e)
    return []
  }
}

// ==================== Thresholds ====================

export const fetchThresholds = async (): Promise<ModelThresholds> => {
  const response = await fetch(apiUrl('/api/thresholds'))
  const raw = await handleResponse<any>(response)
  try {
    return adaptThresholds(raw)
  } catch (e) {
    console.error('fetchThresholds adapt failed:', e)
    return adaptThresholds({})
  }
}

export const saveThresholds = async (
  thresholds: ModelThresholds,
): Promise<ModelThresholds> => {
  const body = reverseAdaptThresholds(thresholds)
  const response = await fetch(apiUrl('/api/thresholds'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const raw = await handleResponse<any>(response)
  try {
    return adaptThresholds(raw)
  } catch (e) {
    console.error('saveThresholds adapt failed:', e)
    return adaptThresholds({})
  }
}

// ==================== Forensic Search ====================

export type ForensicSearchPayload = {
  imageFile: File
  threshold?: number
  from?: string
  to?: string
  cameraIds?: string[]
  gender?: Gender | 'all'
  ageRange?: number[]
  wearingMask?: boolean
  wearingGlasses?: boolean
}

export const runForensicSearch = async (
  payload: ForensicSearchPayload,
): Promise<ForensicMatch[]> => {
  const formData = new FormData()
  formData.append('image', payload.imageFile)
  if (payload.threshold !== undefined) {
    formData.append('threshold', String(payload.threshold))
  }
  if (payload.from) formData.append('date_from', payload.from)
  if (payload.to) formData.append('date_to', payload.to)
  if (payload.cameraIds && payload.cameraIds.length > 0) {
    formData.append('camera_ids', payload.cameraIds.join(','))
  }
  if (payload.gender && payload.gender !== 'all') {
    formData.append('gender', payload.gender)
  }
  if (payload.ageRange && payload.ageRange.length >= 2) {
    formData.append('age_min', String(payload.ageRange[0]))
    formData.append('age_max', String(payload.ageRange[1]))
  }
  if (payload.wearingMask) formData.append('wearing_mask', 'true')
  if (payload.wearingGlasses) formData.append('wearing_glasses', 'true')
  const response = await fetch(forensicApiUrl('/api/forensic/search'), {
    method: 'POST',
    body: formData,
  })
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.matches ?? []
    return arr
      .map((item: any) => {
        try {
          return adaptForensicMatch(item)
        } catch (e) {
          console.error('adaptForensicMatch failed:', e)
          return null
        }
      })
      .filter(Boolean) as ForensicMatch[]
  } catch (e) {
    console.error('runForensicSearch adapter failed:', e)
    return []
  }
}

// ==================== System & Versioning APIs ====================

export async function fetchVersionBundle(): Promise<VersionBundle> {
  const res = await fetch(apiUrl('/api/system/version-bundle'))
  const raw = await handleResponse<any>(res)
  const comps = raw.components || {}
  return {
    detectionModelVersion: strOrEmpty(raw.detection_model_version ?? comps.detection_model),
    embeddingModelVersion: strOrEmpty(raw.embedding_model_version ?? comps.embedding_model),
    galleryVersion: numOrZero(raw.gallery_version ?? comps.gallery_version),
    thresholdVersion: numOrZero(raw.threshold_version ?? comps.threshold_version),
    cameraConfigVersion: numOrZero(raw.camera_config_version ?? comps.camera_config_version),
    algorithmVersion: strOrEmpty(raw.algorithm_version ?? comps.algorithm_version),
    versionBundleHash: strOrEmpty(raw.version_bundle_hash ?? raw.bundle_hash),
    isProductionReady: boolOrFalse(raw.is_production_ready ?? true),
    createdAt: strOrEmpty(raw.created_at),
  }
}

export async function fetchNodeHealth(): Promise<NodeHealthReport[]> {
  const res = await fetch(apiUrl('/api/nodes/health'))
  const raw = await handleResponse<any>(res)
  const nodes = Array.isArray(raw) ? raw : (raw.nodes || [])
  return nodes.map((n: any) => {
    const m = n.metrics || {}
    return {
      nodeId: strOrEmpty(n.node_id ?? n.nodeId ?? n.device_id),
      hostname: n.hostname ? strOrEmpty(n.hostname) : undefined,
      status: strOrEmpty(n.status || 'ONLINE'),
      cpuPercent: numOrZero(n.cpu_percent ?? m.cpu_percent),
      gpuPercent: numOrZero(n.gpu_percent ?? m.gpu_percent),
      memoryPercent: numOrZero(n.memory_percent ?? m.memory_percent),
      temperatureC: n.temperature_c !== undefined && n.temperature_c !== null ? numOrZero(n.temperature_c) : (m.temperature_c !== undefined ? numOrZero(m.temperature_c) : undefined),
      diskUsagePercent: numOrZero(n.disk_usage_percent ?? m.disk_usage_percent),
      diskFreeMb: numOrZero(n.disk_free_mb ?? m.disk_free_mb),
      cameraFps: numOrZero(n.camera_fps ?? m.camera_fps),
      inferenceFps: numOrZero(n.inference_fps ?? m.inference_fps),
      networkLatencyMs: numOrZero(n.network_latency_ms ?? m.network_latency_ms),
      syncQueueLength: numOrZero(n.sync_queue_length ?? m.sync_queue_length),
      eventBacklog: numOrZero(n.event_backlog ?? m.event_backlog),
      recognitionLatencyMs: numOrZero(n.recognition_latency_ms ?? m.recognition_latency_ms),
      runtimeMode: strOrEmpty(n.runtime_mode ?? n.mode ?? 'NORMAL'),
      frameSamplingRate: numOrZero(n.frame_sampling_rate ?? m.frame_sampling_rate ?? 1.0),
      syncBatchSize: numOrZero(n.sync_batch_size ?? m.sync_batch_size ?? 50),
      syncIntervalSeconds: numOrZero(n.sync_interval_seconds ?? m.sync_interval_seconds ?? 1.0),
      reportedAt: strOrEmpty(n.reported_at ?? n.last_heartbeat),
    }
  })
}

export async function fetchProvenance(eventId: string): Promise<RecognitionProvenance> {
  const res = await fetch(apiUrl(`/api/detections/${encodeURIComponent(eventId)}/provenance`))
  const raw = await handleResponse<any>(res)
  return {
    eventId: strOrEmpty(raw.event_id),
    detectionId: raw.detection_id ? strOrEmpty(raw.detection_id) : undefined,
    cameraId: strOrEmpty(raw.camera_id),
    frameReference: strOrEmpty(raw.frame_reference),
    trackId: strOrEmpty(raw.track_id) || 'untracked',
    observationCount: numOrZero(raw.observation_count) || (Array.isArray(raw.observation_references) ? raw.observation_references.length : 0),
    observationReferences: Array.isArray(raw.observation_references) ? raw.observation_references : [],
    detectionModelVersion: strOrEmpty(raw.detection_model_version),
    embeddingModelVersion: strOrEmpty(raw.embedding_model_version),
    embeddingFingerprint: strOrEmpty(raw.embedding_fingerprint),
    candidateMatches: Array.isArray(raw.candidate_matches)
      ? raw.candidate_matches.map((c: any) => ({
          identity: strOrEmpty(c.identity),
          similarity: numOrZero(c.similarity ?? c.score),
          rank: numOrZero(c.rank),
        }))
      : [],
    selectedIdentity: strOrEmpty(raw.selected_identity),
    confidence: numOrZero(raw.confidence),
    decisionTier: strOrEmpty(raw.decision_tier),
    cameraConfigVersion: numOrZero(raw.camera_config_version),
    cloudRecordId: raw.cloud_record_id ? strOrEmpty(raw.cloud_record_id) : undefined,
    decisionTimestamp: strOrEmpty(raw.decision_timestamp),
    provenanceChainHash: strOrEmpty(raw.provenance_chain_hash),
    stages: Array.isArray(raw.stages)
      ? raw.stages.map((s: any) => ({
          stage: strOrEmpty(s.stage),
          timestamp: strOrEmpty(s.timestamp),
          metadata: s.metadata || {},
        }))
      : [],
  }
}

export async function fetchCameraConfig(cameraId: string): Promise<CameraConfigProfile> {
  const res = await fetch(apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/config`))
  const raw = await handleResponse<any>(res)
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id),
    version: numOrZero(raw.version),
    detectionThreshold: numOrZero(raw.detection_threshold),
    recognitionThreshold: numOrZero(raw.recognition_threshold),
    qualityThreshold: numOrZero(raw.quality_threshold),
    samplingRate: numOrZero(raw.sampling_rate),
    temporalWindow: numOrZero(raw.temporal_window),
    isActive: boolOrFalse(raw.is_active),
    createdAt: strOrEmpty(raw.created_at),
    updatedAt: raw.updated_at ? strOrEmpty(raw.updated_at) : undefined,
  }
}

export async function saveCameraConfig(
  cameraId: string,
  config: Partial<CameraConfigProfile>,
): Promise<CameraConfigProfile> {
  const payload: Record<string, any> = {}
  if (config.detectionThreshold !== undefined) payload.detection_threshold = config.detectionThreshold
  if (config.recognitionThreshold !== undefined) payload.recognition_threshold = config.recognitionThreshold
  if (config.qualityThreshold !== undefined) payload.quality_threshold = config.qualityThreshold
  if (config.samplingRate !== undefined) payload.sampling_rate = config.samplingRate
  if (config.temporalWindow !== undefined) payload.temporal_window = config.temporalWindow

  const res = await fetch(apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/config`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const raw = await handleResponse<any>(res)
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id),
    version: numOrZero(raw.version),
    detectionThreshold: numOrZero(raw.detection_threshold),
    recognitionThreshold: numOrZero(raw.recognition_threshold),
    qualityThreshold: numOrZero(raw.quality_threshold),
    samplingRate: numOrZero(raw.sampling_rate),
    temporalWindow: numOrZero(raw.temporal_window),
    isActive: boolOrFalse(raw.is_active),
    createdAt: strOrEmpty(raw.created_at),
    updatedAt: raw.updated_at ? strOrEmpty(raw.updated_at) : undefined,
  }
}

export async function rollbackCameraConfig(
  cameraId: string,
  version?: number,
): Promise<CameraConfigProfile> {
  const endpoint = version !== undefined
    ? `/api/cameras/${encodeURIComponent(cameraId)}/config/rollback/${version}`
    : `/api/cameras/${encodeURIComponent(cameraId)}/config/rollback`
  const res = await fetch(apiUrl(endpoint), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_version: version }),
  })
  const raw = await handleResponse<any>(res)
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id),
    version: numOrZero(raw.version),
    detectionThreshold: numOrZero(raw.detection_threshold),
    recognitionThreshold: numOrZero(raw.recognition_threshold),
    qualityThreshold: numOrZero(raw.quality_threshold),
    samplingRate: numOrZero(raw.sampling_rate),
    temporalWindow: numOrZero(raw.temporal_window),
    isActive: boolOrFalse(raw.is_active),
    createdAt: strOrEmpty(raw.created_at),
    updatedAt: raw.updated_at ? strOrEmpty(raw.updated_at) : undefined,
  }
}

// ==================== WebSocket Connections ====================

export const connectAlertsWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('alerts'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = () => console.warn(`WebSocket unavailable: ${wsUrl('alerts')}`)
  return ws
}

export const connectCamerasWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('cameras'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = () => console.warn(`WebSocket unavailable: ${wsUrl('cameras')}`)
  return ws
}

export const connectKpisWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('kpis'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = () => console.warn(`WebSocket unavailable: ${wsUrl('kpis')}`)
  return ws
}

export { API_URL, WS_URL }

