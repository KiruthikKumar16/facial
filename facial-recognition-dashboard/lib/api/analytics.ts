import { apiUrl, authFetch, handleResponse } from './config';
import type { SystemKpis, FootfallBucket, SubjectTrajectory, MovementNetwork, DuplicateCandidate, DemographicSlice, AttendanceRecord } from '../types';

import { adaptKpis, adaptFootfallBucket, adaptSubjectTrajectory, adaptDuplicateCandidate, adaptDemographicSlice, adaptAttendanceRecord } from './adapters';

export const fetchKpis = async (): Promise<SystemKpis> => {
  const response = await authFetch('/api/kpis')
  const raw = await handleResponse<unknown>(response)
  try {
    return adaptKpis(raw)
  } catch (e) {
    console.error('adaptKpis failed:', e)
    return adaptKpis({})
  }
}

export const fetchDuplicates = async (): Promise<DuplicateCandidate[]> => {
  const response = await authFetch('/api/analytics/duplicates')
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.duplicates ?? []
    return arr
      .map((item: unknown) => {
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
  const response = await authFetch(`/api/analytics/trajectory${qs}`)
  const raw = await handleResponse<unknown>(response)
  try {
    return raw ? adaptSubjectTrajectory(raw) : null
  } catch (e) {
    console.error('fetchTrajectory adapt failed:', e)
    return null
  }
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
  const response = await authFetch(`/api/analytics/footfall${qs}`)
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.buckets ?? raw?.footfall ?? []
    return arr
      .map((item: unknown) => {
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
  const response = await authFetch(`/api/analytics/gender-distribution${query}`)
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.distribution ?? raw?.slices ?? []
    return arr
      .map((item: unknown) => {
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
  const response = await authFetch(`/api/analytics/attendance${qs}`)
  const raw = await handleResponse<unknown>(response)
  try {
    const arr = Array.isArray(raw) ? raw : raw?.records ?? raw?.attendance ?? []
    return arr
      .map((item: unknown) => {
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

export const fetchMovementNetwork = async (): Promise<MovementNetwork> => {
  const response = await authFetch('/api/analytics/movement-network')
  const raw = await handleResponse<unknown>(response)
  try {
    const edges = Array.isArray(raw?.edges) ? raw.edges : []
    return {
      edges: edges.map((edge: unknown) => ({
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

