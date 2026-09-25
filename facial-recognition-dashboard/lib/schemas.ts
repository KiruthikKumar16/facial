import { z } from 'zod';
import { AVATAR_TONES, hashString, normalizeRole } from './api/config';
import type { ProfileRole } from './types';

// Helpers
const strOrEmpty = z.string().nullish().transform(v => v || '');
const numOrZero = z.coerce.number().nullish().transform(v => v || 0);
const boolOrFalse = z.coerce.boolean().nullish().transform(v => v || false);

// Converts 0.0-1.0 to 0-100%
const confidenceTransform = z.coerce.number().nullish().transform(v => {
  if (v === undefined || v === null) return 0;
  return v > 1 ? v : v * 100;
});

// Enums
export const SystemHealthSchema = z.enum(['green', 'yellow', 'red']).catch('red');
export const DetectionStatusSchema = z.enum(['recognized', 'flagged', 'unknown']).catch('unknown');
export const ProfileRoleSchema = z.enum(['employee', 'vip', 'visitor', 'blacklist', 'watchlist']).catch('visitor');
export const EmbeddingStatusSchema = z.enum(['indexed', 'pending', 'stale', 'missing']).catch('missing');
export const GenderSchema = z.enum(['male', 'female', 'unknown']).catch('unknown');
export const CameraStatusSchema = z.enum(['online', 'degraded', 'offline']).catch('offline');
export const AgeBracketSchema = z.enum(['0-17', '18-25', '26-35', '36-50', '51-65', '65+']).catch('0-17');

// Models
export const CameraSchema = z.object({
  id: strOrEmpty,
  name: strOrEmpty,
  zone: strOrEmpty,
  ip_address: z.string().optional(),
  ipAddress: z.string().optional(),
  rtsp_url: z.string().optional(),
  rtspUrl: z.string().optional(),
  status: CameraStatusSchema,
  ping_ms: z.number().optional(),
  pingMs: z.number().optional(),
  frame_latency_ms: z.number().optional(),
  frameLatencyMs: z.number().optional(),
  fps: numOrZero,
  gpu_load: z.number().optional(),
  gpuLoad: z.number().optional(),
  cpu_load: z.number().optional(),
  cpuLoad: z.number().optional(),
  last_heartbeat: z.string().optional(),
  lastHeartbeat: z.string().optional(),
  detections_today: z.number().optional(),
  detectionsToday: z.number().optional()
}).transform(raw => ({
  id: raw.id,
  name: raw.name,
  zone: raw.zone,
  ipAddress: raw.ip_address ?? raw.ipAddress ?? '',
  rtspUrl: raw.rtsp_url ?? raw.rtspUrl ?? '',
  status: raw.status,
  pingMs: raw.ping_ms ?? raw.pingMs ?? 0,
  frameLatencyMs: raw.frame_latency_ms ?? raw.frameLatencyMs ?? 0,
  fps: raw.fps,
  gpuLoad: raw.gpu_load ?? raw.gpuLoad ?? 0,
  cpuLoad: raw.cpu_load ?? raw.cpuLoad ?? 0,
  lastHeartbeat: raw.last_heartbeat ?? raw.lastHeartbeat ?? '',
  detectionsToday: raw.detections_today ?? raw.detectionsToday ?? 0
}));

export const FaceLogSchema = z.object({
  id: strOrEmpty,
  camera_id: z.string().optional(),
  cameraId: z.string().optional(),
  camera_name: z.string().optional(),
  cameraName: z.string().optional(),
  timestamp: strOrEmpty,
  status: DetectionStatusSchema,
  confidence: confidenceTransform,
  liveness_score: z.number().optional(),
  livenessScore: z.number().optional(),
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().nullable().optional(),
  profileName: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  age: numOrZero,
  gender: GenderSchema,
  wearing_mask: z.boolean().optional(),
  wearingMask: z.boolean().optional(),
  wearing_glasses: z.boolean().optional(),
  wearingGlasses: z.boolean().optional(),
  snapshot_tone: z.string().optional(),
  snapshotTone: z.string().optional()
}).transform(raw => ({
  id: raw.id,
  cameraId: raw.camera_id ?? raw.cameraId ?? '',
  cameraName: raw.camera_name ?? raw.cameraName ?? '',
  timestamp: raw.timestamp,
  status: raw.status,
  confidence: raw.confidence,
  livenessScore: Math.max(raw.liveness_score ?? raw.livenessScore ?? 0, 0),
  profileId: raw.profile_id ?? raw.profileId ?? null,
  profileName: raw.profile_name ?? raw.profileName ?? null,
  role: raw.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
  age: raw.age,
  gender: raw.gender,
  wearingMask: raw.wearing_mask ?? raw.wearingMask ?? false,
  wearingGlasses: raw.wearing_glasses ?? raw.wearingGlasses ?? false,
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length]
}));

export const AlertSchema = z.object({
  id: strOrEmpty,
  log_id: z.string().optional(),
  logId: z.string().optional(),
  camera_id: z.string().optional(),
  cameraId: z.string().optional(),
  camera_name: z.string().optional(),
  cameraName: z.string().optional(),
  timestamp: strOrEmpty,
  severity: z.enum(['critical', 'high', 'medium']).catch('medium'),
  reason: strOrEmpty,
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().optional(),
  profileName: z.string().optional(),
  role: z.string().optional(),
  confidence: confidenceTransform,
  acknowledged: boolOrFalse,
  snapshot_tone: z.string().optional(),
  snapshotTone: z.string().optional()
}).transform(raw => ({
  id: raw.id,
  logId: raw.log_id ?? raw.logId ?? '',
  cameraId: raw.camera_id ?? raw.cameraId ?? '',
  cameraName: raw.camera_name ?? raw.cameraName ?? '',
  timestamp: raw.timestamp,
  severity: raw.severity,
  reason: raw.reason,
  profileId: raw.profile_id ?? raw.profileId ?? null,
  profileName: raw.profile_name ?? raw.profileName ?? '',
  role: normalizeRole(raw.role ?? ''),
  confidence: raw.confidence,
  acknowledged: raw.acknowledged,
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length]
}));

export const ProfileSchema = z.object({
  id: strOrEmpty,
  name: strOrEmpty,
  role: z.string().optional(),
  department: strOrEmpty,
  embedding_status: z.string().optional(),
  embeddingStatus: z.string().optional(),
  embedding_count: z.number().optional(),
  embeddingCount: z.number().optional(),
  enrolled_at: z.string().optional(),
  enrolledAt: z.string().optional(),
  last_seen: z.string().nullable().optional(),
  lastSeen: z.string().nullable().optional(),
  age: numOrZero,
  gender: GenderSchema,
  avatar_tone: z.string().optional(),
  avatarTone: z.string().optional(),
  notes: z.string().optional()
}).transform(raw => ({
  id: raw.id,
  name: raw.name,
  role: normalizeRole(raw.role ?? ''),
  department: raw.department,
  embeddingStatus: (['indexed', 'pending', 'stale', 'missing'].includes(raw.embedding_status ?? raw.embeddingStatus ?? '') 
    ? (raw.embedding_status ?? raw.embeddingStatus) 
    : 'missing') as unknown,
  embeddingCount: raw.embedding_count ?? raw.embeddingCount ?? 0,
  enrolledAt: raw.enrolled_at ?? raw.enrolledAt ?? '',
  lastSeen: raw.last_seen ?? raw.lastSeen ?? null,
  age: raw.age,
  gender: raw.gender,
  avatarTone: raw.avatar_tone ?? raw.avatarTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length],
  notes: raw.notes
}));

export const UnregisteredSubjectSchema = z.object({
  id: strOrEmpty,
  display_name: z.string().optional(),
  displayName: z.string().optional(),
  capture_count: z.number().optional(),
  captureCount: z.number().optional(),
  first_seen: z.string().optional(),
  firstSeen: z.string().optional(),
  last_seen: z.string().optional(),
  lastSeen: z.string().optional(),
  cameras: z.array(z.string()).catch([]),
  best_confidence: z.number().optional(),
  bestConfidence: z.number().optional(),
  representative_fingerprint: z.string().optional(),
  representativeFingerprint: z.string().optional(),
  vector_dimension: z.number().optional(),
  vectorDimension: z.number().optional(),
  event_ids: z.array(z.string()).optional(),
  eventIds: z.array(z.string()).optional(),
  status: strOrEmpty
}).transform(raw => ({
  id: raw.id,
  displayName: raw.display_name ?? raw.displayName ?? '',
  captureCount: raw.capture_count ?? raw.captureCount ?? 0,
  firstSeen: raw.first_seen ?? raw.firstSeen ?? '',
  lastSeen: raw.last_seen ?? raw.lastSeen ?? '',
  cameras: raw.cameras,
  bestConfidence: raw.best_confidence ?? raw.bestConfidence ?? 0,
  representativeFingerprint: raw.representative_fingerprint ?? raw.representativeFingerprint ?? '',
  vectorDimension: raw.vector_dimension ?? raw.vectorDimension ?? 0,
  eventIds: raw.event_ids ?? raw.eventIds ?? [],
  status: raw.status
}));

export const DuplicateCandidateSchema = z.object({
  id: strOrEmpty,
  profileA: z.any(),
  profile_a: z.any(),
  profileB: z.any(),
  profile_b: z.any(),
  cosine_similarity: z.number().optional(),
  cosineSimilarity: z.number().optional(),
  shared_sightings: z.number().optional(),
  sharedSightings: z.number().optional()
}).transform(raw => {
  const pA = raw.profileA ?? raw.profile_a ?? {};
  const pB = raw.profileB ?? raw.profile_b ?? {};
  return {
    id: raw.id,
    profileA: {
      id: pA.id ?? '',
      name: pA.name ?? '',
      role: normalizeRole(pA.role ?? ''),
      avatarTone: pA.avatar_tone ?? pA.avatarTone ?? AVATAR_TONES[hashString(pA.id ?? '') % AVATAR_TONES.length],
    },
    profileB: {
      id: pB.id ?? '',
      name: pB.name ?? '',
      role: normalizeRole(pB.role ?? ''),
      avatarTone: pB.avatar_tone ?? pB.avatarTone ?? AVATAR_TONES[hashString(pB.id ?? '') % AVATAR_TONES.length],
    },
    cosineSimilarity: raw.cosine_similarity ?? raw.cosineSimilarity ?? 0,
    sharedSightings: raw.shared_sightings ?? raw.sharedSightings ?? 0
  };
});

export const TrajectoryNodeSchema = z.object({
  camera_id: z.string().optional(),
  cameraId: z.string().optional(),
  camera_name: z.string().optional(),
  cameraName: z.string().optional(),
  zone: strOrEmpty,
  timestamp: strOrEmpty,
  confidence: confidenceTransform,
  snapshot_tone: z.string().optional(),
  snapshotTone: z.string().optional()
}).transform(raw => ({
  cameraId: raw.camera_id ?? raw.cameraId ?? '',
  cameraName: raw.camera_name ?? raw.cameraName ?? '',
  zone: raw.zone,
  timestamp: raw.timestamp,
  confidence: raw.confidence,
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? ''
}));

export const SubjectTrajectorySchema = z.object({
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().optional(),
  profileName: z.string().optional(),
  role: z.string().nullable().optional(),
  path: z.array(TrajectoryNodeSchema).catch([])
}).transform(raw => ({
  profileId: raw.profile_id ?? raw.profileId ?? null,
  profileName: raw.profile_name ?? raw.profileName ?? '',
  role: raw.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
  path: raw.path
}));

export const MovementEdgeSchema = z.object({
  from_camera_id: z.string().optional(),
  fromCameraId: z.string().optional(),
  from_camera_name: z.string().optional(),
  fromCameraName: z.string().optional(),
  to_camera_id: z.string().optional(),
  toCameraId: z.string().optional(),
  to_camera_name: z.string().optional(),
  toCameraName: z.string().optional(),
  count: numOrZero,
  last_seen: z.string().optional(),
  lastSeen: z.string().optional(),
  average_travel_seconds: z.number().optional(),
  averageTravelSeconds: z.number().optional()
}).transform(raw => ({
  fromCameraId: raw.from_camera_id ?? raw.fromCameraId ?? '',
  fromCameraName: raw.from_camera_name ?? raw.fromCameraName ?? '',
  toCameraId: raw.to_camera_id ?? raw.toCameraId ?? '',
  toCameraName: raw.to_camera_name ?? raw.toCameraName ?? '',
  count: raw.count,
  lastSeen: raw.last_seen ?? raw.lastSeen ?? '',
  averageTravelSeconds: raw.average_travel_seconds ?? raw.averageTravelSeconds ?? 0
}));

export const MovementNetworkSchema = z.object({
  edges: z.array(MovementEdgeSchema).catch([])
});

export const ForensicMatchSchema = z.object({
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().optional(),
  profileName: z.string().optional(),
  role: z.string().nullable().optional(),
  cosine_similarity: z.number().optional(),
  cosineSimilarity: z.number().optional(),
  last_seen: z.string().optional(),
  lastSeen: z.string().optional(),
  camera_name: z.string().optional(),
  cameraName: z.string().optional(),
  avatar_tone: z.string().optional(),
  avatarTone: z.string().optional()
}).transform(raw => ({
  profileId: raw.profile_id ?? raw.profileId ?? null,
  profileName: raw.profile_name ?? raw.profileName ?? '',
  role: raw.role ? normalizeRole(raw.role, null as unknown as ProfileRole) : null,
  cosineSimilarity: raw.cosine_similarity ?? raw.cosineSimilarity ?? 0,
  lastSeen: raw.last_seen ?? raw.lastSeen ?? '',
  cameraName: raw.camera_name ?? raw.cameraName ?? '',
  avatarTone: raw.avatar_tone ?? raw.avatarTone ?? AVATAR_TONES[hashString(raw.profile_id ?? raw.profileId ?? '') % AVATAR_TONES.length]
}));

export const AttendanceRecordSchema = z.object({
  profile_id: z.string().optional(),
  profileId: z.string().optional(),
  profile_name: z.string().optional(),
  profileName: z.string().optional(),
  role: z.string().optional(),
  department: strOrEmpty,
  check_in: z.string().optional(),
  checkIn: z.string().optional(),
  check_out: z.string().optional(),
  checkOut: z.string().optional(),
  total_sightings: z.number().optional(),
  totalSightings: z.number().optional(),
  avatar_tone: z.string().optional(),
  avatarTone: z.string().optional()
}).transform(raw => ({
  profileId: raw.profile_id ?? raw.profileId ?? '',
  profileName: raw.profile_name ?? raw.profileName ?? '',
  role: normalizeRole(raw.role ?? ''),
  department: raw.department,
  checkIn: raw.check_in ?? raw.checkIn ?? '',
  checkOut: raw.check_out ?? raw.checkOut ?? '',
  totalSightings: raw.total_sightings ?? raw.totalSightings ?? 0,
  avatarTone: raw.avatar_tone ?? raw.avatarTone ?? AVATAR_TONES[hashString(raw.profile_id ?? raw.profileId ?? '') % AVATAR_TONES.length]
}));

export const FootfallBucketSchema = z.object({
  hour: strOrEmpty,
  detections: numOrZero,
  recognized: numOrZero,
  unknown: numOrZero
});

export const DemographicSliceSchema = z.object({
  label: strOrEmpty,
  value: numOrZero
});

export const SystemKpisSchema = z.object({
  connectedCameras: numOrZero,
  totalCameras: numOrZero,
  detectionsToday: numOrZero,
  activeAlerts: numOrZero,
  systemHealth: SystemHealthSchema,
  gpuLoad: numOrZero,
  cpuLoad: numOrZero,
  avgLatencyMs: numOrZero,
  connected_cameras: z.number().optional(),
  total_cameras: z.number().optional(),
  detections_today: z.number().optional(),
  active_alerts: z.number().optional(),
  system_health: SystemHealthSchema.optional(),
  gpu_load: z.number().optional(),
  cpu_load: z.number().optional(),
  avg_latency_ms: z.number().optional()
}).transform(raw => ({
  connectedCameras: raw.connected_cameras ?? raw.connectedCameras,
  totalCameras: raw.total_cameras ?? raw.totalCameras,
  detectionsToday: raw.detections_today ?? raw.detectionsToday,
  activeAlerts: raw.active_alerts ?? raw.activeAlerts,
  systemHealth: raw.system_health ?? raw.systemHealth ?? 'red',
  gpuLoad: raw.gpu_load ?? raw.gpuLoad,
  cpuLoad: raw.cpu_load ?? raw.cpuLoad,
  avgLatencyMs: raw.avg_latency_ms ?? raw.avgLatencyMs
}));

export const ModelThresholdsSchema = z.object({
  recognitionConfidence: numOrZero,
  livenessScore: numOrZero,
  unknownFaceRetentionDays: numOrZero,
  autoAlertOnBlacklist: boolOrFalse,
  recognition_confidence: z.number().optional(),
  liveness_score: z.number().optional(),
  unknown_face_retention_days: z.number().optional(),
  auto_alert_on_blacklist: z.boolean().optional()
}).transform(raw => ({
  recognitionConfidence: raw.recognition_confidence ?? raw.recognitionConfidence,
  livenessScore: raw.liveness_score ?? raw.livenessScore,
  unknownFaceRetentionDays: raw.unknown_face_retention_days ?? raw.unknownFaceRetentionDays,
  autoAlertOnBlacklist: raw.auto_alert_on_blacklist ?? raw.autoAlertOnBlacklist
}));

export const UnknownCaptureSchema = z.object({
  id: strOrEmpty,
  camera_id: z.string().optional(),
  cameraId: z.string().optional(),
  camera_name: z.string().optional(),
  cameraName: z.string().optional(),
  timestamp: strOrEmpty,
  confidence: confidenceTransform,
  liveness_score: z.number().optional(),
  livenessScore: z.number().optional(),
  age: numOrZero,
  gender: GenderSchema,
  snapshot_tone: z.string().optional(),
  snapshotTone: z.string().optional()
}).transform(raw => ({
  id: raw.id,
  cameraId: raw.camera_id ?? raw.cameraId ?? '',
  cameraName: raw.camera_name ?? raw.cameraName ?? '',
  timestamp: raw.timestamp,
  confidence: raw.confidence,
  livenessScore: Math.max(raw.liveness_score ?? raw.livenessScore ?? 0, 0),
  age: raw.age,
  gender: raw.gender,
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length]
}));

