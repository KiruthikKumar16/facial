'use client'

import { useState, useEffect } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { TopNav } from './top-nav'
import { AlertsTab } from './tabs/alerts-tab'
import { ForensicTab } from './tabs/forensic-tab'
import { ProfilesTab } from './tabs/profiles-tab'
import { AnalyticsTab } from './tabs/analytics-tab'
import { SystemTab } from './tabs/system-tab'
import { CctvAuditPanel } from './cctv-audit-panel'
import { CctvPersonsTab } from './tabs/cctv-persons-tab'
import { ErrorBoundary } from '@/components/ui/error-boundary'
import { useQueryClient } from '@tanstack/react-query'
import {
  connectAlertsWebSocket,
  connectCamerasWebSocket,
  connectKpisWebSocket,
  adaptFaceLog,
  adaptUnknownCapture,
} from '@/lib/api'
import {
  DashboardModeProvider,
  useDashboardMode,
} from '@/lib/mode-context'
import {
  Siren,
  Search,
  HardDrive,
  UsersRound,
  ChartColumnBig,
  ServerCog,
  X,
  Radio,
  ScanFace,
  FileText,
} from 'lucide-react'
import { ExportReportModal } from './export-report-modal'

const LIVE_TABS = [
  { value: 'alerts', label: 'Live Feeds & Alerts', icon: Siren },
  { value: 'profiles', label: 'Vector Management', icon: UsersRound },
  { value: 'analytics', label: 'Live Analytics', icon: ChartColumnBig },
  { value: 'system', label: 'System Health', icon: ServerCog },
] as const

const ARCHIVE_TABS = [
  { value: 'audit', label: 'CCTV Audit & Ingest', icon: HardDrive },
  { value: 'footage-persons', label: 'Footage Detected Persons', icon: ScanFace },
  { value: 'forensic', label: 'Forensic Trajectory Search', icon: Search },
  { value: 'alerts', label: 'Archive Event Trail', icon: Siren },
  { value: 'analytics', label: 'Historical Analytics', icon: ChartColumnBig },
] as const

function DashboardInner() {
  const { mode, setMode } = useDashboardMode()
  const [tab, setTab] = useState<string>('alerts')
  const [showExportModal, setShowExportModal] = useState<boolean>(false)
  const [liveSentryAlert, setLiveSentryAlert] = useState<{
    id: string
    cameraName: string
    profileName: string | null
    status: string
    timestamp: string
  } | null>(null)

  const queryClient = useQueryClient()

  // Switch default active tab when mode toggles
  useEffect(() => {
    if (mode === 'archive') {
      if (tab === 'system' || tab === 'profiles') {
        setTab('audit')
      }
    } else {
      if (tab === 'audit' || tab === 'footage-persons' || tab === 'forensic') {
        setTab('alerts')
      }
    }
  }, [mode])

  // Custom event listener for inter-tab deep navigation
  useEffect(() => {
    const handleTabSwitch = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (detail && typeof detail === 'string') {
        setTab(detail)
      }
    }
    window.addEventListener('switch-dashboard-tab', handleTabSwitch)
    return () => window.removeEventListener('switch-dashboard-tab', handleTabSwitch)
  }, [])

  // Global WebSocket Sentry listener (always listening regardless of mode)
  useEffect(() => {
    const wsAlerts = connectAlertsWebSocket((data: unknown) => {
      const alertData = data as Record<string, unknown> | null
      if (alertData && alertData.id) {
        try {
          const newLog = adaptFaceLog(alertData)

          // If in Archive mode and an alert comes from a live camera, trigger Live Sentry banner
          if (
            mode === 'archive' &&
            (newLog.status === 'flagged' || (newLog as any).role === 'blacklist' || (newLog as any).role === 'watchlist')
          ) {
            setLiveSentryAlert({
              id: newLog.id,
              cameraName: newLog.cameraName,
              profileName: newLog.profileName,
              status: newLog.status,
              timestamp: newLog.timestamp,
            })
          }

          queryClient.setQueryData(['face-logs'], (oldData: unknown) => {
            const list = Array.isArray(oldData) ? oldData : []
            return [newLog, ...list].slice(0, 100)
          })

          if (newLog.status === 'unknown') {
            const newUnknown = adaptUnknownCapture(alertData)
            queryClient.setQueryData(['unknown-captures'], (oldData: unknown) => {
              const list = Array.isArray(oldData) ? oldData : []
              return [newUnknown, ...list].slice(0, 100)
            })
          }
        } catch (e) {
          console.error('WebSocket adaptation error:', e)
        }
        queryClient.invalidateQueries({ queryKey: ['alerts'] })
      } else {
        queryClient.invalidateQueries({ queryKey: ['alerts'] })
        queryClient.invalidateQueries({ queryKey: ['face-logs'] })
        queryClient.invalidateQueries({ queryKey: ['unknown-captures'] })
      }
    })

    const wsCameras = connectCamerasWebSocket(() => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] })
    })

    const wsKpis = connectKpisWebSocket(() => {
      queryClient.invalidateQueries({ queryKey: ['kpis'] })
      queryClient.invalidateQueries({ queryKey: ['footfall'] })
      queryClient.invalidateQueries({ queryKey: ['attendance'] })
      queryClient.invalidateQueries({ queryKey: ['gender-dist'] })
    })

    return () => {
      wsAlerts.close()
      wsCameras.close()
      wsKpis.close()
    }
  }, [queryClient, mode])

  const activeTabs = mode === 'live' ? LIVE_TABS : ARCHIVE_TABS

  return (
    <div className="min-h-screen">
      <TopNav />

      {/* Floating Live Sentry Alert Banner (Interruption if live alert happens while viewing archive) */}
      {liveSentryAlert && mode === 'archive' && (
        <div className="fixed bottom-6 right-6 z-50 flex max-w-md items-center gap-3 rounded-xl border border-destructive/50 bg-card/95 p-4 shadow-2xl backdrop-blur-md animate-in slide-in-from-bottom-5">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-destructive/20 text-destructive ring-1 ring-destructive/40">
            <Radio className="size-5 animate-pulse" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-destructive animate-ping" />
              <p className="text-[11px] font-bold uppercase tracking-wider text-destructive">
                Live Security Alert
              </p>
            </div>
            <p className="text-xs font-semibold text-foreground truncate mt-0.5">
              {liveSentryAlert.profileName ? `${liveSentryAlert.profileName} Flagged` : 'Suspicious Target Detected'}
            </p>
            <p className="text-[10px] text-muted-foreground truncate">
              Camera: {liveSentryAlert.cameraName} &bull; Just now
            </p>
          </div>
          <div className="flex flex-col gap-1 shrink-0">
            <Button
              size="sm"
              variant="destructive"
              className="h-7 text-xs font-semibold px-2.5"
              onClick={() => {
                setMode('live')
                setTab('alerts')
                setLiveSentryAlert(null)
              }}
            >
              View Live
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-[10px] text-muted-foreground hover:text-foreground"
              onClick={() => setLiveSentryAlert(null)}
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as string)} className="gap-0">
        <div className="sticky top-[73px] z-20 border-b border-border bg-background/80 px-2 backdrop-blur-md lg:px-4">
          <div className="flex items-center justify-between">
            <TabsList
              variant="line"
              className="h-auto w-full justify-start gap-0 overflow-x-auto"
            >
              {activeTabs.map(({ value, label, icon: Icon }) => (
                <TabsTrigger
                  key={value}
                  value={value}
                  className="h-11 gap-2 px-3.5 text-muted-foreground data-active:text-foreground"
                >
                  <Icon className="size-4" />
                  <span className="whitespace-nowrap">{label}</span>
                </TabsTrigger>
              ))}
            </TabsList>

            {mode === 'archive' && (
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => setShowExportModal(true)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/40 bg-gradient-to-r from-amber-500/20 via-amber-600/20 to-amber-500/30 px-3 py-1 text-xs font-semibold text-amber-400 hover:bg-amber-500/30 hover:text-amber-300 transition-all shadow-sm shadow-amber-500/10 cursor-pointer"
                >
                  <FileText className="size-3.5" />
                  <span>Export Report</span>
                </Button>
                <span className="hidden lg:inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-500">
                  <HardDrive className="size-3" />
                  <span>Forensic Investigation Mode</span>
                </span>
              </div>
            )}
          </div>
        </div>

        <main className="mx-auto w-full p-4 lg:p-6">
          <TabsContent value="alerts">
            <ErrorBoundary><AlertsTab /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="forensic">
            <ErrorBoundary><ForensicTab /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="audit">
            <ErrorBoundary><CctvAuditPanel /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="footage-persons">
            <ErrorBoundary><CctvPersonsTab onNavigateToForensic={(name) => setTab('forensic')} /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="profiles">
            <ErrorBoundary><ProfilesTab /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="analytics">
            <ErrorBoundary><AnalyticsTab /></ErrorBoundary>
          </TabsContent>
          <TabsContent value="system">
            <ErrorBoundary><SystemTab /></ErrorBoundary>
          </TabsContent>
        </main>
      </Tabs>

      <ExportReportModal
        isOpen={showExportModal}
        onClose={() => setShowExportModal(false)}
      />
    </div>
  )
}

export function Dashboard() {
  return (
    <DashboardModeProvider>
      <DashboardInner />
    </DashboardModeProvider>
  )
}
