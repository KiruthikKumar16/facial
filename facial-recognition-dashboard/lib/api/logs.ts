import { apiUrl, authFetch, handleResponse } from './config';
import type { FaceLog, Alert, UnknownCapture, UnregisteredSubject, ProfileRole } from '../types';

import { adaptFaceLog, adaptAlert, adaptUnknownCapture, adaptUnregisteredSubject } from './adapters';

export const fetchFaceLogs = async (
  limit: number = 100,
  offset: number = 0,
): Promise<FaceLog[]> => {
  const qs = `?limit=${encodeURIComponent(String(limit))}&offset=${encodeURIComponent(String(offset))}`
  const response = await authFetch(`/api/logs${qs}`)
  const raw = await handleResponse<unknown>(response)
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

export const fetchAlerts = async (limit: number = 50): Promise<Alert[]> => {
  const qs = `?limit=${encodeURIComponent(String(limit))}`
  const response = await authFetch(`/api/alerts${qs}`)
  const raw = await handleResponse<unknown>(response)
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
  const raw = await handleResponse<unknown>(response)
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
  const raw = await handleResponse<unknown>(response)
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
  await handleResponse<unknown>(response)
}

export const deleteUnregisteredEvent = async (subjectId: string, eventId: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(subjectId)}/events/${encodeURIComponent(eventId)}`, {
    method: 'DELETE',
  })
  await handleResponse<unknown>(response)
}

export const deleteUnregisteredSubject = async (id: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
  await handleResponse<unknown>(response)
}

export const mergeUnregisteredSubjects = async (id: string, sourceId: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sourceId }),
  })
  await handleResponse<unknown>(response)
}

export const registerUnregisteredSubject = async (id: string, { name, role }: { name: string; role: ProfileRole }): Promise<void> => {
  const formData = new FormData()
  formData.append('id', id)
  formData.append('name', name)
  formData.append('role', role)
  const response = await authFetch(`/api/unregistered-subjects/register`, {
    method: 'POST',
    body: formData,
  })
  await handleResponse<unknown>(response)
}

export const renameUnregisteredSubject = async (id: string, name: string): Promise<void> => {
  const response = await authFetch(`/api/unregistered-subjects/${encodeURIComponent(id)}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  await handleResponse<unknown>(response)
}

