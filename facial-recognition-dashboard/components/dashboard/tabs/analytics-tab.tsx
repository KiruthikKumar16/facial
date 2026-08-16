'use client'

import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  fetchAgeDistribution,
  fetchAttendance,
  fetchFootfall,
  fetchGenderDistribution,
} from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  FaceTile,
  RoleBadge,
  SectionHeading,
} from '@/components/dashboard/shared'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatClock } from '@/lib/format'
import {
  ChartColumnBig,
  Clock,
  PieChart as PieIcon,
  Users,
} from 'lucide-react'

const AGE_COLORS = [
  'var(--chart-4)',
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-5)',
  'var(--muted-foreground)',
]
const GENDER_COLORS = ['var(--chart-4)', 'var(--chart-1)', 'var(--muted-foreground)']

const tooltipStyle = {
  backgroundColor: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontSize: '12px',
  color: 'var(--popover-foreground)',
}

function FootfallChart() {
  const { data = [] } = useQuery({ queryKey: ['footfall'], queryFn: fetchFootfall })
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={ChartColumnBig}
          title="Footfall Heatmap"
          description="Hourly detection volume · recognized vs unknown"
        />
      </CardHeader>
      <CardContent className="p-4">
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} barCategoryGap={4}>
              <XAxis
                dataKey="hour"
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border)' }}
              />
              <YAxis
                tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={32}
              />
              <RTooltip
                contentStyle={tooltipStyle}
                cursor={{ fill: 'var(--muted)', opacity: 0.3 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar
                dataKey="recognized"
                stackId="a"
                fill="var(--chart-3)"
                name="Recognized"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                dataKey="unknown"
                stackId="a"
                fill="var(--chart-2)"
                name="Unknown"
                radius={[3, 3, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

function DemographicPie({
  title,
  queryKey,
  queryFn,
  colors,
}: {
  title: string
  queryKey: string
  queryFn: () => Promise<{ label: string; value: number }[]>
  colors: string[]
}) {
  const { data = [] } = useQuery({ queryKey: [queryKey], queryFn })
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading icon={PieIcon} title={title} />
      </CardHeader>
      <CardContent className="p-4">
        <div className="h-56 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="label"
                innerRadius={45}
                outerRadius={78}
                paddingAngle={2}
                stroke="var(--card)"
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={colors[i % colors.length]} />
                ))}
              </Pie>
              <RTooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}

function AttendanceTable() {
  const { data = [] } = useQuery({
    queryKey: ['attendance'],
    queryFn: fetchAttendance,
  })
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Clock}
          title="Attendance Aggregator"
          count={data.length}
          description="Auto-derived first-seen (check-in) and last-seen (check-out)"
        />
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Individual</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>Check-in</TableHead>
              <TableHead>Check-out</TableHead>
              <TableHead className="pr-4 text-right">Sightings</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((r) => (
              <TableRow key={r.profileId}>
                <TableCell className="pl-4">
                  <div className="flex items-center gap-2.5">
                    <FaceTile tone={r.avatarTone} size="sm" />
                    <div>
                      <p className="text-sm">{r.profileName}</p>
                      <p className="font-mono text-[11px] text-muted-foreground">
                        {r.profileId}
                      </p>
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <RoleBadge role={r.role} />
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {r.department}
                </TableCell>
                <TableCell className="font-mono text-xs text-success">
                  {formatClock(r.checkIn)}
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground">
                  {formatClock(r.checkOut)}
                </TableCell>
                <TableCell className="pr-4 text-right font-mono text-sm tabular-nums">
                  {r.totalSightings}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function AnalyticsTab() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <FootfallChart />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <DemographicPie
            title="Age Groups"
            queryKey="age-dist"
            queryFn={fetchAgeDistribution}
            colors={AGE_COLORS}
          />
          <DemographicPie
            title="Gender Ratio"
            queryKey="gender-dist"
            queryFn={fetchGenderDistribution}
            colors={GENDER_COLORS}
          />
        </div>
      </div>
      <AttendanceTable />
    </div>
  )
}
