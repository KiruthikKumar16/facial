import { z } from 'zod';
import { AVATAR_TONES, hashString, normalizeRole } from './api/config';
import type { ProfileRole } from './types';

// Helpers
export const strOrEmpty = z.string().nullish().transform(v => v || '');
export const numOrZero = z.coerce.number().nullish().transform(v => v || 0);
export const boolOrFalse = z.coerce.boolean().nullish().transform(v => v || false);

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
  ip_address: strOrEmpty,
  ipAddress: strOrEmpty,
  rtsp_url: strOrEmpty,
  rtspUrl: strOrEmpty,
  status: CameraStatusSchema,
  ping_ms: numOrZero.optional(),
  pingMs: numOrZero.optional(),
  frame_latency_ms: numOrZero.optional(),
  frameLatencyMs: numOrZero.optional(),
  fps: numOrZero,
  gpu_load: numOrZero.optional(),
  gpuLoad: numOrZero.optional(),
  cpu_load: numOrZero.optional(),
  cpuLoad: numOrZero.optional(),
  last_heartbeat: strOrEmpty.optional(),
  lastHeartbeat: strOrEmpty.optional(),
  detections_today: numOrZero.optional(),
  detectionsToday: numOrZero.optional()
}).transform(raw => ({
  id: raw.id,
  name: raw.name,
  zone: raw.zone,
  ipAddress: raw.ip_address || raw.ipAddress || '',
  rtspUrl: raw.rtsp_url || raw.rtspUrl || '',
  status: raw.status,
  pingMs: raw.ping_ms ?? raw.pingMs ?? 0,
  frameLatencyMs: raw.frame_latency_ms ?? raw.frameLatencyMs ?? 0,
  fps: raw.fps,
  gpuLoad: raw.gpu_load ?? raw.gpuLoad ?? 0,
  cpuLoad: raw.cpu_load ?? raw.cpuLoad ?? 0,
  lastHeartbeat: raw.last_heartbeat || raw.lastHeartbeat || '',
  detectionsToday: raw.detections_today ?? raw.detectionsToday ?? 0
}));

export const FaceLogSchema = z.object({
  id: strOrEmpty,
  camera_id: z.string().nullish(),
  cameraId: z.string().nullish(),
  camera_name: z.string().nullish(),
  cameraName: z.string().nullish(),
  timestamp: strOrEmpty,
  status: DetectionStatusSchema,
  confidence: confidenceTransform,
  liveness_score: z.number().nullish(),
  livenessScore: z.number().nullish(),
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().nullable().optional(),
  profileName: z.string().nullable().optional(),
  role: z.string().nullable().optional(),
  age: numOrZero,
  gender: GenderSchema,
  wearing_mask: z.boolean().nullish(),
  wearingMask: z.boolean().nullish(),
  wearing_glasses: z.boolean().nullish(),
  wearingGlasses: z.boolean().nullish(),
  snapshot_tone: z.string().nullish(),
  snapshotTone: z.string().nullish(),
  face_image: z.string().nullable().optional(),
  faceImage: z.string().nullable().optional(),
  source: z.enum(['live', 'archive']).nullish(),
  batch_id: z.string().nullable().optional(),
  batchId: z.string().nullable().optional(),
  source_video: z.string().nullable().optional(),
  sourceVideo: z.string().nullable().optional(),
  video_elapsed_sec: z.number().nullable().optional(),
  videoElapsedSec: z.number().nullable().optional(),
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
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length],
  faceImage: raw.face_image ?? raw.faceImage ?? null,
  source: raw.source ?? 'live',
  batchId: raw.batch_id ?? raw.batchId ?? null,
  sourceVideo: raw.source_video ?? raw.sourceVideo ?? null,
  videoElapsedSec: raw.video_elapsed_sec ?? raw.videoElapsedSec ?? null,
}));

export const AlertSchema = z.object({
  id: strOrEmpty,
  log_id: z.string().nullish(),
  logId: z.string().nullish(),
  camera_id: z.string().nullish(),
  cameraId: z.string().nullish(),
  camera_name: z.string().nullish(),
  cameraName: z.string().nullish(),
  timestamp: strOrEmpty,
  severity: z.enum(['critical', 'high', 'medium']).catch('medium'),
  reason: strOrEmpty,
  profile_id: z.string().nullable().optional(),
  profileId: z.string().nullable().optional(),
  profile_name: z.string().nullish(),
  profileName: z.string().nullish(),
  role: z.string().nullish(),
  confidence: confidenceTransform,
  acknowledged: boolOrFalse,
  snapshot_tone: z.string().nullish(),
  snapshotTone: z.string().nullish(),
  source: z.enum(['live', 'archive']).nullish(),
  batch_id: z.string().nullable().optional(),
  batchId: z.string().nullable().optional()
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
  snapshotTone: raw.snapshot_tone ?? raw.snapshotTone ?? AVATAR_TONES[hashString(raw.id) % AVATAR_TONES.length],
  source: raw.source ?? 'live',
  batchId: raw.batch_id ?? raw.batchId ?? null
}));

export const ProfileSchema = z.object({
  id: strOrEmpty,
  name: strOrEmpty,
  role: z.string().nullish(),
  department: strOrEmpty,
  embedding_status: z.string().nullish(),
  embeddingStatus: z.string().nullish(),
  embedding_count: numOrZero.optional(),
  embeddingCount: numOrZero.optional(),
  enrolled_at: z.string().nullish(),
  enrolledAt: z.string().nullish(),
  last_seen: z.string().nullable().optional(),
  lastSeen: z.string().nullable().optional(),
  age: numOrZero,
  gender: GenderSchema,
  avatar_tone: z.string().nullish(),
  avatarTone: z.string().nullish(),
  notes: z.string().nullish()
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
  status: strOrEmpty,
  thumbnail: z.string().nullable().optional(),
  face_image: z.string().nullable().optional()
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
  status: raw.status,
  thumbnail: raw.thumbnail ?? raw.face_image ?? null
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
  profile_id: z.string().nullish(),
  profileId: z.string().nullish(),
  profile_name: z.string().nullish(),
  profileName: z.string().nullish(),
  role: z.string().nullish(),
  department: strOrEmpty,
  check_in: z.string().nullish(),
  checkIn: z.string().nullish(),
  check_out: z.string().nullish(),
  checkOut: z.string().nullish(),
  total_sightings: numOrZero.optional(),
  totalSightings: numOrZero.optional(),
  avatar_tone: z.string().nullish(),
  avatarTone: z.string().nullish()
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
  connected_cameras: numOrZero.optional(),
  total_cameras: numOrZero.optional(),
  detections_today: numOrZero.optional(),
  active_alerts: numOrZero.optional(),
  system_health: SystemHealthSchema.optional(),
  gpu_load: numOrZero.optional(),
  cpu_load: numOrZero.optional(),
  avg_latency_ms: numOrZero.optional()
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
  recognitionConfidence: z.number().optional(),
  livenessScore: z.number().optional(),
  unknownFaceRetentionDays: z.number().optional(),
  autoAlertOnBlacklist: z.boolean().optional(),
  recognition_confidence: z.number().optional(),
  similarity_confidence: z.number().optional(),
  similarityConfidence: z.number().optional(),
  liveness_score: z.number().optional(),
  liveness_threshold: z.number().optional(),
  livenessThreshold: z.number().optional(),
  unknown_face_retention_days: z.number().optional(),
  auto_alert_on_blacklist: z.boolean().optional(),
  age_variance: z.number().optional(),
  ageVariance: z.number().optional()
}).transform(raw => ({
  recognitionConfidence: raw.similarity_confidence ?? raw.similarityConfidence ?? raw.recognition_confidence ?? raw.recognitionConfidence ?? 60,
  livenessScore: raw.liveness_threshold ?? raw.livenessThreshold ?? raw.liveness_score ?? raw.livenessScore ?? 50,
  unknownFaceRetentionDays: raw.unknown_face_retention_days ?? raw.unknownFaceRetentionDays ?? 30,
  autoAlertOnBlacklist: raw.auto_alert_on_blacklist ?? raw.autoAlertOnBlacklist ?? true
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

export const ImportBatchSchema = z.object({
  id: strOrEmpty,
  name: strOrEmpty,
  source_directory: z.string().optional(),
  sourceDirectory: z.string().optional(),
  camera_count: numOrZero.optional(),
  cameraCount: numOrZero.optional(),
  total_files: numOrZero.optional(),
  totalFiles: numOrZero.optional(),
  total_detections: numOrZero.optional(),
  totalDetections: numOrZero.optional(),
  total_alerts: numOrZero.optional(),
  totalAlerts: numOrZero.optional(),
  footage_start: z.string().nullable().optional(),
  footageStart: z.string().nullable().optional(),
  footage_end: z.string().nullable().optional(),
  footageEnd: z.string().nullable().optional(),
  sample_fps: numOrZero.optional(),
  sampleFps: numOrZero.optional(),
  status: strOrEmpty,
  created_at: strOrEmpty.optional(),
  createdAt: strOrEmpty.optional()
}).transform(raw => ({
  id: raw.id,
  name: raw.name,
  sourceDirectory: raw.source_directory ?? raw.sourceDirectory ?? '',
  cameraCount: raw.camera_count ?? raw.cameraCount ?? 0,
  totalFiles: raw.total_files ?? raw.totalFiles ?? 0,
  totalDetections: raw.total_detections ?? raw.totalDetections ?? 0,
  totalAlerts: raw.total_alerts ?? raw.totalAlerts ?? 0,
  footageStart: raw.footage_start ?? raw.footageStart ?? null,
  footageEnd: raw.footage_end ?? raw.footageEnd ?? null,
  sampleFps: raw.sample_fps ?? raw.sampleFps ?? 3.0,
  status: raw.status,
  createdAt: raw.created_at ?? raw.createdAt ?? ''
}));

