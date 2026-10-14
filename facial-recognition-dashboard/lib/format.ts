import type { DetectionStatus, ProfileRole, SystemHealth } from './types'

const DISPLAY_TIME_ZONE = 'Asia/Kolkata'

/** Tailwind gradient utility per synthetic-snapshot tone. */
export const toneGradient: Record<string, string> = {
  sky: 'from-sky-500/40 to-sky-900/60',
  amber: 'from-amber-500/40 to-amber-900/60',
  rose: 'from-rose-500/40 to-rose-900/60',
  violet: 'from-violet-500/40 to-violet-900/60',
  emerald: 'from-emerald-500/40 to-emerald-900/60',
  cyan: 'from-cyan-500/40 to-cyan-900/60',
  orange: 'from-orange-500/40 to-orange-900/60',
  indigo: 'from-indigo-500/40 to-indigo-900/60',
}

export function parseDateSafe(iso: string | undefined | null): Date | null {
  if (!iso) return null
  const s = String(iso).trim()
  if (!s) return null

  // Handle naive timestamps without timezone offset (e.g. "2026-10-12T18:03:01" or "2026-10-12 18:03:01")
  // PostgreSQL TIMESTAMP WITHOUT TIME ZONE stores naive UTC. Treat naive timestamps as UTC (Z) so they convert accurately to IST.
  const naiveMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?$/)
  if (naiveMatch) {
    const utcIso = `${naiveMatch[1]}-${naiveMatch[2]}-${naiveMatch[3]}T${naiveMatch[4]}:${naiveMatch[5]}:${naiveMatch[6]}Z`
    const dUtc = new Date(utcIso)
    if (!isNaN(dUtc.getTime())) return dUtc
  }

  // Normalize excessive microsecond digits while preserving timezone offset (Z or +/-HH:MM)
  const normalized = s.replace(/(\.\d{3})\d+([Z+-].*)?$/, '$1$2')
  let d = new Date(normalized)
  if (!isNaN(d.getTime())) return d

  d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

export function formatTime(iso: string | undefined | null): string {
  const d = parseDateSafe(iso)
  if (!d) return '—'
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: DISPLAY_TIME_ZONE,
  })
}

export function formatDateTime(iso: string | undefined | null): string {
  const d = parseDateSafe(iso)
  if (!d) return '—'
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: DISPLAY_TIME_ZONE,
  })
}

export function formatClock(iso: string | undefined | null): string {
  const d = parseDateSafe(iso)
  if (!d) return '—'
  return d.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: DISPLAY_TIME_ZONE,
  })
}

export function formatNumber(n: number | undefined | null): string {
  if (n === undefined || n === null || typeof n !== 'number' || isNaN(n)) return '—'
  return n.toLocaleString('en-US')
}

export function initials(name: string): string {
  return name
    .replace(/\(.*?\)/g, '')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? '')
    .join('')
}

export const roleLabel: Record<ProfileRole, string> = {
  employee: 'Employee',
  vip: 'VIP',
  visitor: 'Visitor',
  blacklist: 'Blacklist',
  watchlist: 'Watchlist',
}

export const statusLabel: Record<DetectionStatus, string> = {
  recognized: 'Recognized',
  flagged: 'Flagged',
  unknown: 'Unknown',
}

export const healthLabel: Record<SystemHealth, string> = {
  green: 'Nominal',
  yellow: 'Degraded',
  red: 'Critical',
}
