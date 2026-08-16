'use client'

import { useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TopNav } from './top-nav'
import { AlertsTab } from './tabs/alerts-tab'
import { ForensicTab } from './tabs/forensic-tab'
import { ProfilesTab } from './tabs/profiles-tab'
import { AnalyticsTab } from './tabs/analytics-tab'
import { SystemTab } from './tabs/system-tab'
import {
  Siren,
  Search,
  UsersRound,
  ChartColumnBig,
  ServerCog,
} from 'lucide-react'

const TABS = [
  { value: 'alerts', label: 'Alerts & Event Trail', icon: Siren },
  { value: 'forensic', label: 'Forensic Search', icon: Search },
  { value: 'profiles', label: 'Vector Management', icon: UsersRound },
  { value: 'analytics', label: 'Analytics', icon: ChartColumnBig },
  { value: 'system', label: 'System Health', icon: ServerCog },
] as const

export function Dashboard() {
  const [tab, setTab] = useState<string>('alerts')

  return (
    <div className="min-h-screen">
      <TopNav />
      <Tabs value={tab} onValueChange={(v) => setTab(v as string)} className="gap-0">
        <div className="sticky top-[73px] z-20 border-b border-border bg-background/80 px-2 backdrop-blur-md lg:px-4">
          <TabsList
            variant="line"
            className="h-auto w-full justify-start gap-0 overflow-x-auto"
          >
            {TABS.map(({ value, label, icon: Icon }) => (
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
        </div>

        <main className="mx-auto w-full max-w-[1600px] p-4 lg:p-6">
          <TabsContent value="alerts">
            <AlertsTab />
          </TabsContent>
          <TabsContent value="forensic">
            <ForensicTab />
          </TabsContent>
          <TabsContent value="profiles">
            <ProfilesTab />
          </TabsContent>
          <TabsContent value="analytics">
            <AnalyticsTab />
          </TabsContent>
          <TabsContent value="system">
            <SystemTab />
          </TabsContent>
        </main>
      </Tabs>
    </div>
  )
}
