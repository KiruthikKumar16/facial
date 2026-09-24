/**
 * Real API client for facial recognition backend.
 *
 * Supports both local development and cloud deployment:
 * - Local: http://localhost:8000
 * - Render: https://facial-api.render.com
 *
 * Configure via environment variables:
 * NEXT_PUBLIC_API_URL - Base API URL (default: http://localhost:8000)
 * NEXT_PUBLIC_WS_URL - WebSocket URL (default: ws://localhost:8000)
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
  ProvenanceCandidate,
  ProvenanceStage,
  RecognitionProvenance,
  SubjectTrajectory,
  SystemKpis,
  SystemHealth,
  TrajectoryNode,
  UnknownCapture,
  UnregisteredSubject,
  VersionBundle,
} from './types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'

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
  const logs = await fetchFaceLogs(100)
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

/** Format a Date as an IST ISO string (with +05:30 offset) instead of UTC. */
function toISTISOString(date: Date): string {
  // IST is UTC+5:30
  const istOffsetMs = 5.5 * 60 * 60 * 1000
  const istDate = new Date(date.getTime() + istOffsetMs)
  const iso = istDate.toISOString().replace('Z', '+05:30')
  return iso
}

export const fetchFootfall = async (
  days?: number,
  date_from?: Date,
  date_to?: Date
): Promise<FootfallBucket[]> => {
  const params = new URLSearchParams()

  if (days !== undefined) {
    params.append('days', String(days))
  }

  if (date_from !== undefined) {
    params.append('date_from', toISTISOString(date_from))
  }

  if (date_to !== undefined) {
    params.append('date_to', toISTISOString(date_to))
  }

  const qs = params.toString() ? `?${params.toString()}` : ''
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


export const fetchGenderDistribution = async (dateFrom?: string, dateTo?: string): Promise<DemographicSlice[]> => {
  const params = new URLSearchParams()
  if (dateFrom) params.append('date_from', dateFrom)
  if (dateTo) params.append('date_to', dateTo)
  const query = params.toString() ? `?${params.toString()}` : ''
  const response = await fetch(apiUrl(`/api/analytics/gender-distribution${query}`))
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

export const fetchAttendance = async (
  days?: number,
  date_from?: Date,
  date_to?: Date
): Promise<AttendanceRecord[]> => {
  const params = new URLSearchParams()
  if (days !== undefined) {
    params.append('days', String(days))
  }
  if (date_from !== undefined) {
    params.append('date_from', toISTISOString(date_from))
  }
  if (date_to !== undefined) {
    params.append('date_to', toISTISOString(date_to))
  }
  
  const qs = params.toString() ? `?${params.toString()}` : ''
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
  imageFile?: File
  profileId?: string
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
  if (payload.imageFile) {
    formData.append('image', payload.imageFile)
  }
  if (payload.profileId) {
    formData.append('profile_id', payload.profileId)
  }
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
  const response = await fetch(apiUrl('/api/forensic/search'), {
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

// ==================== Camera Configuration ====================

export const fetchCameraConfig = async (cameraId: string): Promise<CameraConfigProfile> => {
  const response = await fetch(apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/config`))
  const raw = await handleResponse<any>(response)
  try {
    return {
      id: strOrEmpty(raw.id),
      cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
      version: numOrZero(raw.version),
      detectionThreshold: numOrZero(raw.detection_threshold ?? raw.detectionThreshold),
      recognitionThreshold: numOrZero(raw.recognition_threshold ?? raw.recognitionThreshold),
      qualityThreshold: numOrZero(raw.quality_threshold ?? raw.qualityThreshold),
      samplingRate: numOrZero(raw.sampling_rate ?? raw.samplingRate),
      temporalWindow: numOrZero(raw.temporal_window ?? raw.temporalWindow),
      isActive: boolOrFalse(raw.is_active ?? raw.isActive),
      createdAt: strOrEmpty(raw.created_at ?? raw.createdAt),
      updatedAt: strOrEmpty(raw.updated_at ?? raw.updatedAt) || undefined,
    }
  } catch (e) {
    console.error('fetchCameraConfig adapt failed:', e)
    throw e
  }
}

export const saveCameraConfig = async (cameraId: string, config: Partial<CameraConfigProfile>): Promise<CameraConfigProfile> => {
  const response = await fetch(apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/config`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      detectionThreshold: config.detectionThreshold,
      recognitionThreshold: config.recognitionThreshold,
      qualityThreshold: config.qualityThreshold,
      samplingRate: config.samplingRate,
      temporalWindow: config.temporalWindow,
      isActive: config.isActive,
    }),
  })
  const raw = await handleResponse<any>(response)
  try {
    return {
      id: strOrEmpty(raw.id),
      cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
      version: numOrZero(raw.version),
      detectionThreshold: numOrZero(raw.detection_threshold ?? raw.detectionThreshold),
      recognitionThreshold: numOrZero(raw.recognition_threshold ?? raw.recognitionThreshold),
      qualityThreshold: numOrZero(raw.quality_threshold ?? raw.qualityThreshold),
      samplingRate: numOrZero(raw.sampling_rate ?? raw.samplingRate),
      temporalWindow: numOrZero(raw.temporal_window ?? raw.temporalWindow),
      isActive: boolOrFalse(raw.is_active ?? raw.isActive),
      createdAt: strOrEmpty(raw.created_at ?? raw.createdAt),
      updatedAt: strOrEmpty(raw.updated_at ?? raw.updatedAt) || undefined,
    }
  } catch (e) {
    console.error('saveCameraConfig adapt failed:', e)
    throw e
  }
}

export const rollbackCameraConfig = async (cameraId: string): Promise<CameraConfigProfile> => {
  const response = await fetch(apiUrl(`/api/cameras/${encodeURIComponent(cameraId)}/config/rollback`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  const raw = await handleResponse<any>(response)
  return {
    id: strOrEmpty(raw.id),
    cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
    version: numOrZero(raw.version),
    detectionThreshold: numOrZero(raw.detection_threshold ?? raw.detectionThreshold),
    recognitionThreshold: numOrZero(raw.recognition_threshold ?? raw.recognitionThreshold),
    qualityThreshold: numOrZero(raw.quality_threshold ?? raw.qualityThreshold),
    samplingRate: numOrZero(raw.sampling_rate ?? raw.samplingRate),
    temporalWindow: numOrZero(raw.temporal_window ?? raw.temporalWindow),
    isActive: boolOrFalse(raw.is_active ?? raw.isActive),
    createdAt: strOrEmpty(raw.created_at ?? raw.createdAt),
    updatedAt: strOrEmpty(raw.updated_at ?? raw.updatedAt) || undefined,
  }
}

// ==================== Lineage & Provenance ====================

export const fetchProvenance = async (eventId: string): Promise<RecognitionProvenance> => {
  const response = await fetch(apiUrl(`/api/detections/${encodeURIComponent(eventId)}/provenance`))
  const raw = await handleResponse<any>(response)
  try {
    // Simplified adaptation - in reality this would be more complex
    return {
      eventId: strOrEmpty(raw.event_id ?? raw.eventId),
      detectionId: strOrEmpty(raw.detection_id ?? raw.detectionId) || undefined,
      cameraId: strOrEmpty(raw.camera_id ?? raw.cameraId),
      frameReference: strOrEmpty(raw.frame_reference ?? raw.frameReference),
      trackId: strOrEmpty(raw.track_id ?? raw.trackId),
      observationCount: numOrZero(raw.observation_count ?? raw.observationCount),
      observationReferences: Array.isArray(raw.observation_references ?? raw.observationReferences)
        ? (raw.observation_references ?? raw.observationReferences)
        : [],
      detectionModelVersion: strOrEmpty(raw.detection_model_version ?? raw.detectionModelVersion),
      embeddingModelVersion: strOrEmpty(raw.embedding_model_version ?? raw.embeddingModelVersion),
      embeddingFingerprint: strOrEmpty(raw.embedding_fingerprint ?? raw.embeddingFingerprint),
      candidateMatches: Array.isArray(raw.candidate_matches ?? raw.candidateMatches)
        ? (raw.candidate_matches ?? raw.candidateMatches).map((match: any) => ({
            identity: strOrEmpty(match.identity),
            similarity: numOrZero(match.similarity),
            rank: numOrZero(match.rank),
          }))
        : [],
      selectedIdentity: strOrEmpty(raw.selected_identity ?? raw.selectedIdentity),
      confidence: numOrZero(raw.confidence),
      decisionTier: strOrEmpty(raw.decision_tier ?? raw.decisionTier),
      cameraConfigVersion: numOrZero(raw.camera_config_version ?? raw.cameraConfigVersion),
      cloudRecordId: strOrEmpty(raw.cloud_record_id ?? raw.cloudRecordId) || undefined,
      decisionTimestamp: strOrEmpty(raw.decision_timestamp ?? raw.decisionTimestamp),
      provenanceChainHash: strOrEmpty(raw.provenance_chain_hash ?? raw.provenanceChainHash),
      stages: Array.isArray(raw.stages)
        ? raw.stages.map((stage: any) => ({
            stage: strOrEmpty(stage.stage),
            timestamp: strOrEmpty(stage.timestamp),
            metadata: stage.metadata || {},
          }))
        : [],
    }
  } catch (e) {
    console.error('fetchProvenance adapt failed:', e)
    throw e
  }
}

// ==================== Unregistered Subjects ====================

export function adaptUnregisteredSubject(raw: any): UnregisteredSubject {
  return {
    id: strOrEmpty(raw.id),
    displayName: strOrEmpty(raw.display_name ?? raw.displayName ?? raw.name ?? ''),
    captureCount: numOrZero(raw.capture_count ?? raw.captureCount),
    firstSeen: strOrEmpty(raw.first_seen ?? raw.firstSeen),
    lastSeen: strOrEmpty(raw.last_seen ?? raw.lastSeen),
    cameras: Array.isArray(raw.cameras) ? raw.cameras : typeof raw.cameras === 'string' ? [raw.cameras] : [],
    bestConfidence: numOrZero(raw.best_confidence ?? raw.bestConfidence),
    representativeFingerprint: strOrEmpty(raw.representative_fingerprint ?? raw.representativeFingerprint ?? raw.fingerprint ?? ''),
    vectorDimension: numOrZero(raw.vector_dimension ?? raw.vectorDimension),
    eventIds: Array.isArray(raw.event_ids ?? raw.eventIds) ? (raw.event_ids ?? raw.eventIds) : [],
    status: strOrEmpty(raw.status ?? 'unknown'),
  };
}

export const fetchUnregisteredSubjects = async (): Promise<UnregisteredSubject[]> => {
  const response = await fetch(apiUrl('/api/unregistered-subjects'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : [] // maybe raw?.unregisteredSubjects ?? []
    return arr.map((item: any) => {
      try {
        return adaptUnregisteredSubject(item)
      } catch (e) {
        console.error('adaptUnregisteredSubject failed:', e)
        return null
      }
    }).filter(Boolean) as UnregisteredSubject[]
  } catch (e) {
    console.error('fetchUnregisteredSubjects adapter failed:', e)
    return []
  }
}

export const assignUnregisteredSubject = async (id: string, profileId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/assign`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profileId }),
  })
  await handleResponse<any>(response)
}

export const deleteUnregisteredEvent = async (subjectId: string, eventId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(subjectId)}/events/${encodeURIComponent(eventId)}`), {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const deleteUnregisteredSubject = async (id: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}`), {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const mergeUnregisteredSubjects = async (id: string, sourceId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/merge`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sourceId }),
  })
  await handleResponse<any>(response)
}

export const registerUnregisteredSubject = async (id: string, { name, role }: { name: string; role: ProfileRole }): Promise<void> => {
  const formData = new FormData()
  formData.append('id', id)
  formData.append('name', name)
  formData.append('role', role)
  const response = await fetch(apiUrl(`/api/unregistered-subjects/register`), {
    method: 'POST',
    body: formData,
  })
  await handleResponse<any>(response)
}

export const renameUnregisteredSubject = async (id: string, name: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/unregistered-subjects/${encodeURIComponent(id)}/rename`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  await handleResponse<any>(response)
}

// ==================== System ====================

export const fetchMovementNetwork = async (): Promise<MovementNetwork> => {
  const response = await fetch(apiUrl('/api/analytics/movement-network'))
  const raw = await handleResponse<any>(response)
  try {
    const edges = Array.isArray(raw?.edges) ? raw.edges : []
    return {
      edges: edges.map((edge: any) => ({
        fromCameraId: strOrEmpty(edge.from_camera_id ?? edge.fromCameraId),
        fromCameraName: strOrEmpty(edge.from_camera_name ?? edge.fromCameraName),
        toCameraId: strOrEmpty(edge.to_camera_id ?? edge.toCameraId),
        toCameraName: strOrEmpty(edge.to_camera_name ?? edge.toCameraName),
        count: numOrZero(edge.count),
        lastSeen: strOrEmpty(edge.last_seen ?? edge.lastSeen),
        averageTravelSeconds: numOrZero(edge.average_travel_seconds ?? edge.averageTravelSeconds),
      }))
    }
  } catch (e) {
    console.error('fetchMovementNetwork adapt failed:', e)
    throw e
  }
}

export const fetchNodeHealth = async (): Promise<NodeHealthReport[]> => {
  const response = await fetch(apiUrl('/api/nodes/health'))
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.nodes ?? []
    return arr
      .map((item: any) => {
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

// ==================== System Info ====================

export const fetchVersionBundle = async (): Promise<VersionBundle> => {
  const response = await fetch(apiUrl('/api/system/version-bundle'))
  const raw = await handleResponse<any>(response)
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

// ==================== Profiles (additional) ====================

export const deleteProfile = async (profileId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`), {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const deleteProfileEmbeddings = async (profileId: string): Promise<void> => {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}/embeddings`), {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const updateProfile = async (profileId: string, { name, role, department }: { name: string; role: ProfileRole; department: string }): Promise<void> => {
  const response = await fetch(apiUrl(`/api/profiles/${encodeURIComponent(profileId)}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, role, department }),
  })
  await handleResponse<any>(response)
}

// ==================== WebSocket Connections ====================

export const connectAlertsWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('alerts'))
  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      onMessage(message.data)
    } catch (parseError) {
      console.error('WebSocket message parse error:', parseError)
    }
  }
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
  return ws
}

export const connectCamerasWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('cameras'))
  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      onMessage(message.data)
    } catch (parseError) {
      console.error('WebSocket message parse error:', parseError)
    }
  }
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
  return ws
}

export const connectKpisWebSocket = (
  onMessage: (data: any) => void,
): WebSocket => {
  const ws = new WebSocket(wsUrl('kpis'))
  ws.onmessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      onMessage(message.data)
    } catch (parseError) {
      console.error('WebSocket message parse error:', parseError)
    }
  }
  ws.onerror = (error) => {
    console.error('WebSocket error:', error)
  }
  return ws
}

export { API_URL, WS_URL }
