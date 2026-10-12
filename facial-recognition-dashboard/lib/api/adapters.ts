import { apiUrl, authFetch, handleResponse, strOrEmpty, numOrZero, boolOrFalse } from './config';
import {
  CameraSchema, FaceLogSchema, AlertSchema, UnknownCaptureSchema, ProfileSchema,
  UnregisteredSubjectSchema, DuplicateCandidateSchema, SubjectTrajectorySchema,
  TrajectoryNodeSchema, MovementEdgeSchema, MovementNetworkSchema, ForensicMatchSchema,
  AttendanceRecordSchema, FootfallBucketSchema, DemographicSliceSchema,
  SystemKpisSchema, ModelThresholdsSchema
} from '../schemas';

export function adaptCamera(raw: unknown) {
  return CameraSchema.parse(raw);
}

export function adaptFaceLog(raw: unknown) {
  return FaceLogSchema.parse(raw);
}

export function adaptAlert(raw: unknown) {
  return AlertSchema.parse(raw);
}

export function adaptUnknownCapture(raw: unknown) {
  return UnknownCaptureSchema.parse(raw);
}

export function adaptProfile(raw: unknown) {
  return ProfileSchema.parse(raw);
}

export function adaptUnregisteredSubject(raw: unknown) {
  return UnregisteredSubjectSchema.parse(raw);
}

export function adaptDuplicateCandidate(raw: unknown) {
  return DuplicateCandidateSchema.parse(raw);
}

export function adaptTrajectoryNode(raw: unknown) {
  return TrajectoryNodeSchema.parse(raw);
}

export function adaptSubjectTrajectory(raw: unknown) {
  return SubjectTrajectorySchema.parse(raw);
}

export function adaptMovementEdge(raw: unknown) {
  return MovementEdgeSchema.parse(raw);
}

export function adaptMovementNetwork(raw: unknown) {
  return MovementNetworkSchema.parse(raw);
}

export function adaptForensicMatch(raw: unknown) {
  return ForensicMatchSchema.parse(raw);
}

export function adaptAttendanceRecord(raw: unknown) {
  return AttendanceRecordSchema.parse(raw);
}

export function adaptFootfallBucket(raw: unknown) {
  return FootfallBucketSchema.parse(raw);
}

export function adaptDemographicSlice(raw: unknown) {
  return DemographicSliceSchema.parse(raw);
}

export function adaptKpis(raw: unknown) {
  return SystemKpisSchema.parse(raw);
}

export function adaptThresholds(raw: unknown) {
  return ModelThresholdsSchema.parse(raw);
}


export function reverseAdaptThresholds(t: any) {
  const conf = (t.recognitionConfidence !== undefined && t.recognitionConfidence > 1) 
    ? t.recognitionConfidence / 100 
    : (t.recognitionConfidence ?? t.similarity_confidence ?? 0.60);
  const live = (t.livenessScore !== undefined && t.livenessScore > 1) 
    ? t.livenessScore / 100 
    : (t.livenessScore ?? t.liveness_threshold ?? 0.50);

  return {
    similarity_confidence: conf,
    liveness_threshold: live,
    age_variance: t.ageVariance ?? t.age_variance ?? 5.0,
    recognition_confidence: conf,
    liveness_score: live,
    unknown_face_retention_days: t.unknownFaceRetentionDays ?? t.unknown_face_retention_days ?? 30,
    auto_alert_on_blacklist: t.autoAlertOnBlacklist ?? t.auto_alert_on_blacklist ?? true,
  };
}
