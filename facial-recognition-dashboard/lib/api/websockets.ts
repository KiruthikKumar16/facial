import { WS_URL } from './config';

const wsUrl = (path: string) => {
  const token = typeof window !== 'undefined' ? localStorage.getItem('sentinel_token') : null;
  const base = `${WS_URL}/ws/${path}`;
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
};

export interface ManagedWebSocket {
  close: (code?: number, reason?: string) => void;
  readonly readyState: number;
}

class ReconnectingSocket implements ManagedWebSocket {
  private path: string;
  private onMessage: (data: unknown) => void;
  private ws: WebSocket | null = null;
  private isDisposed = false;
  private retryDelay = 1000;
  private maxRetryDelay = 10000;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private onlineHandler: (() => void) | null = null;

  constructor(path: string, onMessage: (data: unknown) => void) {
    this.path = path;
    this.onMessage = onMessage;
    this.connect();

    if (typeof window !== 'undefined') {
      this.onlineHandler = () => {
        if (!this.isDisposed && (!this.ws || this.ws.readyState === WebSocket.CLOSED)) {
          this.retryDelay = 1000;
          this.connect();
        }
      };
      window.addEventListener('online', this.onlineHandler);
    }
  }

  private connect() {
    if (this.isDisposed) return;
    if (typeof window === 'undefined') return;

    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    try {
      const url = wsUrl(this.path);
      const ws = new WebSocket(url);
      this.ws = ws;

      ws.onopen = () => {
        // Reset delay on successful connection
        this.retryDelay = 1000;
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.onMessage(message.data !== undefined ? message.data : message);
        } catch (parseError) {
          console.warn(`[WS ${this.path}] Parse error:`, parseError);
        }
      };

      ws.onerror = () => {
        // WebSocket onerror will trigger onclose where reconnect is handled
      };

      ws.onclose = () => {
        this.ws = null;
        if (!this.isDisposed) {
          const delay = Math.min(this.retryDelay, this.maxRetryDelay);
          this.retryDelay = Math.min(this.retryDelay * 1.5, this.maxRetryDelay);
          this.timer = setTimeout(() => {
            this.connect();
          }, delay);
        }
      };
    } catch {
      if (!this.isDisposed) {
        this.timer = setTimeout(() => {
          this.connect();
        }, this.retryDelay);
      }
    }
  }

  get readyState(): number {
    return this.ws ? this.ws.readyState : (typeof WebSocket !== 'undefined' ? WebSocket.CLOSED : 3);
  }

  close(code?: number, reason?: string) {
    this.isDisposed = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.onlineHandler && typeof window !== 'undefined') {
      window.removeEventListener('online', this.onlineHandler);
      this.onlineHandler = null;
    }
    if (this.ws) {
      try {
        this.ws.close(code, reason);
      } catch {
        // ignore
      }
      this.ws = null;
    }
  }
}

export const connectAlertsWebSocket = (
  onMessage: (data: unknown) => void,
): ManagedWebSocket => {
  return new ReconnectingSocket('alerts', onMessage);
};

export const connectCamerasWebSocket = (
  onMessage: (data: unknown) => void,
): ManagedWebSocket => {
  return new ReconnectingSocket('cameras', onMessage);
};

export const connectKpisWebSocket = (
  onMessage: (data: unknown) => void,
): ManagedWebSocket => {
  return new ReconnectingSocket('kpis', onMessage);
};
