import type { DetectionStatus, ProfileRole, SystemHealth } from './types'

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

export function formatTime(iso: string | undefined | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

export function formatClock(iso: string | undefined | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
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
