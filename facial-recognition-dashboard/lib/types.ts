/**
 * Core data models for the SENTINEL facial-recognition operations console.
 *
 * These mirror the shape of records returned by the FastAPI / pgvector backend
 * (repo: KiruthikKumar16/facial). They are intentionally serialisable so the
 * same interfaces can be reused on both the API layer and the client.
 */

export type SystemHealth = 'green' | 'yellow' | 'red'

export type DetectionStatus = 'recognized' | 'flagged' | 'unknown'

export type ProfileRole = 'employee' | 'vip' | 'visitor' | 'blacklist' | 'watchlist'

export type EmbeddingStatus = 'indexed' | 'pending' | 'stale' | 'missing'

export type Gender = 'male' | 'female' | 'unknown'

export type CameraStatus = 'online' | 'degraded' | 'offline'

export type AgeBracket = '0-17' | '18-25' | '26-35' | '36-50' | '51-65' | '65+'

export interface Camera {
  id: string
  name: string
  zone: string
  ipAddress: string
  rtspUrl: string
  status: CameraStatus
  /** Round-trip ping to the node in milliseconds. */
  pingMs: number
  /** Per-frame inference latency in milliseconds. */
  frameLatencyMs: number
  /** Frames processed per second. */
  fps: number
  gpuLoad: number
  cpuLoad: number
  lastHeartbeat: string
  detectionsToday: number
}

export interface FaceLog {
  id: string
  cameraId: string
  cameraName: string
  timestamp: string
  status: DetectionStatus
  /** Match confidence 0-100. Null for unknown faces below threshold. */
  confidence: number
  /** Liveness / anti-spoofing score 0-100. */
  livenessScore: number
  profileId: string | null
  profileName: string | null
  role: ProfileRole | null
  age: number
  gender: Gender
  wearingMask: boolean
  wearingGlasses: boolean
  /** Colour token used to render the synthetic face-crop swatch. */
  snapshotTone: string
}

export interface Alert {
  id: string
  logId: string
  cameraId: string
  cameraName: string
  timestamp: string
  severity: 'critical' | 'high' | 'medium'
  reason: string
  profileId: string | null
  profileName: string
  role: ProfileRole
  confidence: number
  acknowledged: boolean
  snapshotTone: string
}

export interface UnknownCapture {
  id: string
  cameraId: string
  cameraName: string
  timestamp: string
  confidence: number
  livenessScore: number
  age: number
  gender: Gender
  snapshotTone: string
}

export interface Profile {
  id: string
  name: string
  role: ProfileRole
  department: string
  embeddingStatus: EmbeddingStatus
  /** Number of enrolled face embeddings for this identity. */
  embeddingCount: number
  enrolledAt: string
  lastSeen: string | null
  age: number
  gender: Gender
  avatarTone: string
  notes?: string
}

export interface DuplicateCandidate {
  id: string
  profileA: Pick<Profile, 'id' | 'name' | 'role' | 'avatarTone'>
  profileB: Pick<Profile, 'id' | 'name' | 'role' | 'avatarTone'>
  /** Cosine similarity of the two embeddings, 0-1. */
  cosineSimilarity: number
  sharedSightings: number
}

export interface TrajectoryNode {
  cameraId: string
  cameraName: string
  zone: string
  timestamp: string
  confidence: number
  snapshotTone: string
}

export interface SubjectTrajectory {
  profileId: string | null
  profileName: string
  role: ProfileRole | null
  path: TrajectoryNode[]
}

export interface ForensicMatch {
  profileId: string | null
  profileName: string
  role: ProfileRole | null
  cosineSimilarity: number
  lastSeen: string
  cameraName: string
  avatarTone: string
}

export interface AttendanceRecord {
  profileId: string
  profileName: string
  role: ProfileRole
  department: string
  checkIn: string
  checkOut: string
  totalSightings: number
  avatarTone: string
}

export interface FootfallBucket {
  hour: string
  detections: number
  recognized: number
  unknown: number
}

export interface DemographicSlice {
  label: string
  value: number
}

export interface SystemKpis {
  connectedCameras: number
  totalCameras: number
  detectionsToday: number
  activeAlerts: number
  systemHealth: SystemHealth
  gpuLoad: number
  cpuLoad: number
  avgLatencyMs: number
}

export interface ModelThresholds {
  recognitionConfidence: number
  livenessScore: number
  unknownFaceRetentionDays: number
  autoAlertOnBlacklist: boolean
}
