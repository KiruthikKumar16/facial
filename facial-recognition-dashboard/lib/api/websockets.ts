import { WS_URL, authFetch, handleResponse, apiUrl } from './config';

const wsUrl = (path: string) => `${WS_URL}/ws/${path}`;

export const connectAlertsWebSocket = (
  onMessage: (data: unknown) => void,
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
  onMessage: (data: unknown) => void,
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
  onMessage: (data: unknown) => void,
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

