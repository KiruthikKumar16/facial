import { apiUrl, authFetch, handleResponse } from './config';
import type { FaceLog, Alert, UnknownCapture, UnregisteredSubject, ProfileRole, CameraEpisode } from '../types';

import { adaptFaceLog, adaptAlert, adaptUnknownCapture, adaptUnregisteredSubject } from './adapters';

export const fetchCameraEpisodes = async (
  limit: number = 100,
  source?: string,
  batchId?: string,
  cameraId?: string,
  profileId?: string,
  gapThreshold: number = 45.0,
  minDwell: number = 0.0,
  minConfidence: number = 0.0,
): Promise<CameraEpisode[]> => {
  let qs = `?limit=${encodeURIComponent(String(limit))}&gap_threshold=${encodeURIComponent(String(gapThreshold))}`
  if (source) qs += `&source=${encodeURIComponent(source)}`
  if (batchId) qs += `&batch_id=${encodeURIComponent(batchId)}`
  if (cameraId) qs += `&camera_id=${encodeURIComponent(cameraId)}`
  if (profileId) qs += `&profile_id=${encodeURIComponent(profileId)}`
  if (minDwell > 0) qs += `&min_dwell=${encodeURIComponent(String(minDwell))}`
  if (minConfidence > 0) qs += `&min_confidence=${encodeURIComponent(String(minConfidence))}`
  const response = await authFetch(`/api/logs/episodes${qs}`)
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.episodes ?? []
    return arr.map((item: any) => ({
      id: String(item.id),
      cameraId: String(item.camera_id),
      cameraName: String(item.camera_name),
      zone: item.zone ? String(item.zone) : undefined,
      subjectId: item.subject_id ? String(item.subject_id) : null,
      subjectName: String(item.subject_name || 'Unidentified'),
      role: item.role ? String(item.role) : 'visitor',
      status: (item.status as any) || 'unknown',
      inTime: String(item.in_time),
      outTime: String(item.out_time),
      dwellSeconds: Number(item.dwell_seconds || 0),
      detectionCount: Number(item.detection_count || 1),
      peakConfidence: Number(item.peak_confidence || 0),
      livenessScore: Number(item.liveness_score || 0),
      inFaceImage: item.in_face_image ? String(item.in_face_image) : null,
      outFaceImage: item.out_face_image ? String(item.out_face_image) : null,
      direction: String(item.direction || 'Stationary / Present'),
      source: (item.source as any) || 'live',
      batchId: item.batch_id ? String(item.batch_id) : null,
      snapshotTone: String(item.snapshot_tone || 'cyan'),
      isActive: Boolean(item.is_active),
      nextCameraId: item.next_camera_id ? String(item.next_camera_id) : null,
      nextCameraName: item.next_camera_name ? String(item.next_camera_name) : null,
      transitSeconds: item.transit_seconds != null ? Number(item.transit_seconds) : null,
      detectionIds: Array.isArray(item.detection_ids) ? item.detection_ids.map(String) : [],
    }))
  } catch (e) {
    console.error('fetchCameraEpisodes failed:', e)
    return []
  }
}

export const fetchFaceLogs = async (
  limit: number = 100,
  offset: number = 0,
  source?: string,
  batchId?: string,
): Promise<FaceLog[]> => {
  let qs = `?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`
  if (source) qs += `&source=${encodeURIComponent(source)}`
  if (batchId) qs += `&batch_id=${encodeURIComponent(batchId)}`
  const response = await authFetch(`/api/logs${qs}`)
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.logs ?? []
    return arr
      .map((item: unknown) => {
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

export const fetchAlerts = async (
  limit: number = 50,
  source?: string,
  batchId?: string,
): Promise<Alert[]> => {
  let qs = `?limit=${encodeURIComponent(String(limit))}`
  if (source) qs += `&source=${encodeURIComponent(source)}`
  if (batchId) qs += `&batch_id=${encodeURIComponent(batchId)}`
  const response = await authFetch(`/api/alerts${qs}`)
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.alerts ?? []
    return arr
      .map((item: unknown) => {
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
  const response = await authFetch(
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

export const fetchUnregisteredSubjects = async (): Promise<UnregisteredSubject[]> => {
  const response = await authFetch('/api/unregistered-subjects')
  const raw = await handleResponse<any>(response)
  try {
    const arr = Array.isArray(raw) ? raw : [] // maybe raw?.unregisteredSubjects ?? []
    return arr.map((item: unknown) => {
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
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profileId }),
  })
  await handleResponse<any>(response)
}

export const deleteUnregisteredEvent = async (subjectId: string, eventId: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(subjectId)}/events/${encodeURIComponent(eventId)}`, {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const deleteUnregisteredSubject = async (id: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  await handleResponse<any>(response)
}

export const mergeUnregisteredSubjects = async (id: string, sourceId: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sourceId }),
  })
  await handleResponse<any>(response)
}

export const registerUnregisteredSubject = async (
  id: string,
  { name, role, department }: { name: string; role: ProfileRole; department?: string },
): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, role, department }),
  })
  await handleResponse<unknown>(response)
}

export const renameUnregisteredSubject = async (id: string, name: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  await handleResponse<any>(response)
}

export const transferSightings = async (
  detectionIds: string[],
  targetSubjectId: string,
): Promise<{ status: string; transferred_count: number; target_type: string; target_name: string }> => {
  const response = await authFetch('/api/unregistered-subjects/transfer-sightings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      detection_ids: detectionIds,
      target_subject_id: targetSubjectId,
    }),
  })
  return handleResponse<{ status: string; transferred_count: number; target_type: string; target_name: string }>(response)
}

