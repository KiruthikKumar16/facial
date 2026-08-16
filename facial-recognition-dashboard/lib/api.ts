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

import type { ForensicMatch, ModelThresholds } from './types'

// Get API URL from environment, fallback to localhost
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'

// Helper to construct API endpoints
function apiUrl(path: string): string {
  return `${API_URL}${path}`
}

function wsUrl(channel: string): string {
  return `${WS_URL}/ws/${channel}`
}

// Error handler
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`)
  }
  return response.json()
}

// ==================== System KPIs ====================

export const fetchKpis = async () => {
  const response = await fetch(apiUrl('/api/kpis'))
  return handleResponse(response)
}

// ==================== Cameras ====================

export const fetchCameras = async () => {
  const response = await fetch(apiUrl('/api/cameras'))
  return handleResponse(response)
}

// ==================== Detection Logs ====================

export const fetchFaceLogs = async (limit: number = 100, offset: number = 0) => {
  const response = await fetch(apiUrl(`/api/logs?limit=${limit}&offset=${offset}`))
  return handleResponse(response)
}

// ==================== Alerts ====================

export const fetchAlerts = async (limit: number = 50) => {
  const response = await fetch(apiUrl(`/api/alerts?limit=${limit}`))
  return handleResponse(response)
}

// ==================== Profiles ====================

export const fetchProfiles = async () => {
  const response = await fetch(apiUrl('/api/profiles'))
  return handleResponse(response)
}

export const fetchProfile = async (profileId: string) => {
  const response = await fetch(apiUrl(`/api/profiles/${profileId}`))
  return handleResponse(response)
}

// ==================== Unknown Captures ====================

export const fetchUnknownCaptures = async () => {
  // Derived from logs with status='unknown'
  const logs = await fetchFaceLogs(100)
  return logs.filter((log: any) => log.status === 'unknown')
}

// ==================== Duplicates & Analytics ====================

export const fetchDuplicates = async () => {
  // TODO: Implement endpoint when available
  return []
}

export const fetchTrajectory = async () => {
  // TODO: Implement endpoint when available
  return null
}

export const fetchFootfall = async () => {
  // TODO: Implement endpoint when available
  return []
}

export const fetchAgeDistribution = async () => {
  // TODO: Implement endpoint when available
  return []
}

export const fetchGenderDistribution = async () => {
  // TODO: Implement endpoint when available
  return []
}

export const fetchAttendance = async () => {
  // TODO: Implement endpoint when available
  return []
}

// ==================== Thresholds ====================

export const fetchThresholds = async () => {
  const response = await fetch(apiUrl('/api/thresholds'))
  return handleResponse(response)
}

export const saveThresholds = async (thresholds: ModelThresholds) => {
  const response = await fetch(apiUrl('/api/thresholds'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(thresholds),
  })
  return handleResponse(response)
}

// ==================== Forensic Search ====================

export const runForensicSearch = async (): Promise<ForensicMatch[]> => {
  // TODO: Implement endpoint when available
  return []
}

// ==================== WebSocket Connections ====================

/**
 * Connect to alerts channel for real-time alert updates.
 * 
 * @param onMessage Callback when new alert arrives
 * @returns WebSocket instance for cleanup
 */
export const connectAlertsWebSocket = (
  onMessage: (data: any) => void
): WebSocket => {
  const ws = new WebSocket(wsUrl('alerts'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = (error) => console.error('WebSocket error:', error)
  return ws
}

/**
 * Connect to cameras channel for live camera health updates.
 */
export const connectCamerasWebSocket = (
  onMessage: (data: any) => void
): WebSocket => {
  const ws = new WebSocket(wsUrl('cameras'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = (error) => console.error('WebSocket error:', error)
  return ws
}

/**
 * Connect to KPIs channel for real-time dashboard updates.
 */
export const connectKpisWebSocket = (
  onMessage: (data: any) => void
): WebSocket => {
  const ws = new WebSocket(wsUrl('kpis'))
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    onMessage(message.data)
  }
  ws.onerror = (error) => console.error('WebSocket error:', error)
  return ws
}

// Export API URL for debugging
export { API_URL, WS_URL }
