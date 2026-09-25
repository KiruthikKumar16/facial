import { apiUrl, authFetch, handleResponse } from './config';
import type { Camera, CameraConfigProfile } from '../types';

import { adaptCamera } from './adapters';

export const fetchCameras = async (): Promise<Camera[]> => {
  const response = await authFetch('/api/cameras')
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.cameras ?? []
    return arr
      .map((item: unknown) => {
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

export const fetchCameraConfig = async (cameraId: string): Promise<CameraConfigProfile> => {
  const response = await authFetch(`/api/cameras/${encodeURIComponent(cameraId)}/config`)
  const raw = await handleResponse<unknown>(response)
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
  const response = await authFetch(`/api/cameras/${encodeURIComponent(cameraId)}/config`, {
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
  const raw = await handleResponse<unknown>(response)
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
  const response = await authFetch(`/api/cameras/${encodeURIComponent(cameraId)}/config/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  const raw = await handleResponse<unknown>(response)
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

