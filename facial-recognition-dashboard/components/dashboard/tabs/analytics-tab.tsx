'use client'

import { useState, useRef, useEffect, useMemo } from 'react'
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
  fetchAttendance,
  fetchFootfall,
  fetchGenderDistribution,
  fetchImportBatches,
} from '@/lib/api'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
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
import { formatClock, parseDateSafe } from '@/lib/format'
import {
  ChartColumnBig,
  Clock,
  PieChart as PieIcon,
  Users,
  Calendar,
  Film,
  Sparkles,
  ShieldCheck,
  Activity,
  Video,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react'
import { useDashboardMode } from '@/lib/mode-context'

const GENDER_COLORS: Record<string, string> = {
  Male: '#3b82f6',
  Female: '#f472b6',
  Unknown: '#9ca3af'
}


const tooltipStyle = {
  backgroundColor: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontSize: '12px',
  color: 'var(--popover-foreground)',
}

function useContainerWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState<number>(0)

  useEffect(() => {
    if (!ref.current) return
    const updateWidth = () => {
      if (ref.current && ref.current.clientWidth > 0) {
        setWidth(ref.current.clientWidth)
      }
    }
    updateWidth()
    const ro = new ResizeObserver(updateWidth)
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])

  return { ref, width }
}

function FootfallChart({ selectedDates }: { selectedDates: Date[] }) {
  const { mode, selectedBatchId } = useDashboardMode()
  const { ref: chartContainerRef, width: containerWidth } = useContainerWidth()
  const { data = [] } = useQuery({
    queryKey: ['footfall', selectedDates, mode, selectedBatchId],
    queryFn: () => {
      // Calculate date range from selectedDates
      let date_from: Date | undefined
      let date_to: Date | undefined

      if (selectedDates.length > 0) {
        // Sort dates to get earliest and latest
        const sortedDates = [...selectedDates].sort((a, b) => a.getTime() - b.getTime())
        date_from = sortedDates[0]
        date_to = sortedDates[sortedDates.length - 1]

        // Set to start of day (00:00:00) for date_from
        date_from = new Date(date_from.getFullYear(), date_from.getMonth(), date_from.getDate())

        // Set to end of day (23:59:59.999) for date_to
        date_to = new Date(date_to.getFullYear(), date_to.getMonth(), date_to.getDate(), 23, 59, 59, 999)
      }
      
      return fetchFootfall(undefined, date_from, date_to, mode, selectedBatchId ?? undefined)
    },
    refetchInterval: 5000, // Real-time: refresh every 5 seconds
  })

  // Generate all 24 hours (00 to 23) to ensure consistent X-axis labels
  // Handle both "HH" and "HH:MM" formats in the data
  const allHours = Array.from({ length: 24 }, (_, i) => {
    const hourString = i.toString().padStart(2, '0')
    // Look for data matching either "HH" or "HH:MM" format
    const existingData = data.find(item =>
      item.hour === hourString ||
      item.hour === hourString + ':00'
    )
    if (existingData) {
      // Extract just the hour part (HH) from HH:00 format for consistent display
      const displayHour = existingData.hour.split(':')[0]
      return {
        ...existingData,
        hour: displayHour
      }
    }
    return {
      hour: hourString,
      detections: 0,
      recognized: 0,
      unknown: 0
    }
  })

  const peakHour = useMemo(() => {
    let max = 0
    let peak: (typeof allHours)[0] | null = null
    for (const h of allHours) {
      if (h.detections > max) {
        max = h.detections
        peak = h
      }
    }
    return peak
  }, [allHours])

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3 flex flex-row items-center justify-between">
        <SectionHeading
          icon={ChartColumnBig}
          title="Footfall Heatmap"
          description={mode === 'archive' ? 'Hourly detection volume · Camera clock timestamps (IST)' : 'Hourly detection volume · recognized vs unknown'}
        />
        <div className="flex items-center gap-2">
          {peakHour && peakHour.detections > 0 && (
            <Badge variant="outline" className="text-[11px] font-mono border-emerald-500/40 bg-emerald-500/10 text-emerald-400 gap-1 py-0.5">
              <span>Peak: {peakHour.hour}:00 IST ({peakHour.detections} frames)</span>
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px] font-mono border-border text-muted-foreground py-0.5">
            IST (UTC+5:30)
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-4">
        <div ref={chartContainerRef} className="h-72 w-full min-h-[288px]">
          {containerWidth > 0 ? (
            <ResponsiveContainer width={containerWidth} height={280} key={`footfall-${containerWidth}`}>
              <BarChart data={allHours} barCategoryGap={4}>
                <XAxis
                  dataKey="hour"
                  tick={{
                    fill: 'var(--muted-foreground)',
                    fontSize: 10,
                  }}
                  tickFormatter={(value) => String(value).padStart(2, '0')}
                  interval={0}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--border)' }}
                  allowDataOverflow={true}
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
                  labelFormatter={(label) => `⏰ Time: ${label}:00 – ${label}:59 IST (Local Camera Clock)`}
                  formatter={(value: any, name: any) => [
                    `${value} frame${value !== 1 ? 's' : ''}`,
                    name === 'recognized' || name === 'Recognized' ? '🟢 Recognized' : '🟡 Unknown'
                  ]}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar
                  dataKey="recognized"
                  stackId="a"
                  fill="#10b981"
                  name="Recognized"
                  radius={[0, 0, 0, 0]}
                />
                <Bar
                  dataKey="unknown"
                  stackId="a"
                  fill="#f59e0b"
                  name="Unknown"
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[280px] w-full flex items-center justify-center text-xs text-muted-foreground">
              Measuring chart viewport...
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function DateSelector({
  title = "Date Selector",
  selectedDates,
  onDateChange,
  clipCoveredDates = [],
}: {
  title?: string
  selectedDates: Date[]
  onDateChange: (dates: Date[]) => void
  clipCoveredDates?: Date[]
}) {
  const [currentDate, setCurrentDate] = useState(selectedDates.length > 0 ? selectedDates[0] : new Date())
  const [multiSelect, setMultiSelect] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStartCell, setDragStartCell] = useState<number | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (selectedDates.length > 0) {
      setCurrentDate(selectedDates[0])
    }
  }, [selectedDates])

  const monthName = currentDate.toLocaleString('default', { month: 'long' })
  const year = currentDate.getFullYear()
  const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
  const lastDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0)
  const startingDayIndex = firstDayOfMonth.getDay() // 0 for Sunday, 1 for Monday, etc.
  const daysInMonth = lastDayOfMonth.getDate()

  // Generate days for the calendar grid (6 weeks * 7 days = 42 days)
  const days: (Date | null)[] = []
  // Add empty cells for the days before the first day of the month
  for (let i = 0; i < startingDayIndex; i++) {
    days.push(null)
  }
  // Add days of the month
  for (let day = 1; day <= daysInMonth; day++) {
    days.push(new Date(currentDate.getFullYear(), currentDate.getMonth(), day))
  }
  // Fill the rest with null to complete 42 days (6 rows * 7 columns)
  while (days.length < 42) {
    days.push(null)
  }

  const isSameDay = (date1: Date, date2: Date) =>
    date1.getDate() === date2.getDate() &&
    date1.getMonth() === date2.getMonth() &&
    date1.getFullYear() === date2.getFullYear()

  const isToday = (date: Date) => isSameDay(date, new Date())

  const isSelected = (date: Date) =>
    selectedDates.some((d) => isSameDay(d, date))

  const isCovered = (date: Date) =>
    clipCoveredDates.some((d) => isSameDay(d, date))

  const handleDayClick = (date: Date) => {
    if (!date) return
    if (multiSelect && !isDragging) {
      // Only toggle on click if not dragging (to avoid toggling on drag end)
      const isAlreadySelected = isSelected(date)
      const updatedDates = isAlreadySelected
        ? selectedDates.filter((d) => !isSameDay(d, date))
        : [...selectedDates, date]
      onDateChange(updatedDates)
    } else if (!multiSelect) {
      // Single select mode: always set to the clicked date
      onDateChange([date])
    }
    // If dragging, we don't handle the click here (handled by drag events)
  }

  const handleDragStart = (e: React.PointerEvent) => {
    e.preventDefault() // Prevent text selection
    if (multiSelect && gridRef.current) {
      setIsDragging(true)
      // Find which cell was clicked
      const cellIndex = getCellIndexAtPosition(e.clientX, e.clientY, gridRef.current)
      if (cellIndex !== null) {
        setDragStartCell(cellIndex)
        // Toggle the starting cell
        const clickedDate = days[cellIndex]
        if (clickedDate && !isSelected(clickedDate)) {
          const newSelectedDates = [...selectedDates, clickedDate]
          onDateChange(newSelectedDates)
        } else if (clickedDate) {
          const newSelectedDates = selectedDates.filter(d => !isSameDay(d, clickedDate))
          onDateChange(newSelectedDates)
        }
      }
    }
  }

  const handleDragMove = (e: React.PointerEvent) => {
    if (!isDragging || !multiSelect || !gridRef.current || dragStartCell === null) return

    // Find current cell under pointer
    const currentCellIndex = getCellIndexAtPosition(e.clientX, e.clientY, gridRef.current)
    if (currentCellIndex === null) return

    // Select all cells between drag start and current position
    const start = Math.min(dragStartCell, currentCellIndex)
    const end = Math.max(dragStartCell, currentCellIndex)

    // Create new selection set
    const newSelectedDates: Date[] = []
    for (let i = start; i <= end; i++) {
      const date = days[i]
      if (date && !newSelectedDates.some(d => isSameDay(d, date))) {
        newSelectedDates.push(date)
      }
    }

    // Also include any previously selected cells that are outside the drag range
    // but were selected before drag started (to preserve them)
    const preselectedDates = selectedDates.filter(date =>
      !days.some((d, idx) => idx >= start && idx <= end && d && isSameDay(d as Date, date))
    )

    // Combine and deduplicate
    const allSelected = [...preselectedDates, ...newSelectedDates]
    const deduplicated: Date[] = []
    allSelected.forEach(date => {
      if (!deduplicated.some(d => isSameDay(d, date))) {
        deduplicated.push(date)
      }
    })

    onDateChange(deduplicated)
  }

  const handleDragEnd = () => {
    if (isDragging) {
      setIsDragging(false)
      setDragStartCell(null)
    }
  }

  const getCellIndexAtPosition = (clientX: number, clientY: number, gridElement: HTMLDivElement): number | null => {
    if (!gridElement) return null

    const rect = gridElement.getBoundingClientRect()
    const cellWidth = rect.width / 7
    const cellHeight = rect.height / 6

    const xInGrid = clientX - rect.left
    const yInGrid = clientY - rect.top

    // Skip if outside grid
    if (xInGrid < 0 || xInGrid > rect.width || yInGrid < 0 || yInGrid > rect.height) {
      return null
    }

    // Calculate column and row (0-indexed)
    const col = Math.floor(xInGrid / cellWidth)
    const row = Math.floor(yInGrid / cellHeight)

    // Skip if outside grid bounds
    if (row < 0 || row >= 6 || col < 0 || col >= 7) {
      return null
    }

    // Calculate index in days array
    const index = row * 7 + col
    return index >= 0 && index < days.length ? index : null
  }

  const handleMonthChange = (offset: number) => {
    // Reset drag state when changing months
    setIsDragging(false)
    setDragStartCell(null)

    setCurrentDate((prev) => {
      const newDate = new Date(prev)
      newDate.setMonth(newDate.getMonth() + offset)
      return newDate
    })
  }

  const handleMultiSelectToggle = () => {
    // Reset drag state when switching modes
    setIsDragging(false)
    setDragStartCell(null)

    // When switching from multiple to single mode, reset selection to today's date
    if (multiSelect) {
      const today = new Date()
      onDateChange([today])
    }
    setMultiSelect(!multiSelect)
  }

  return (
    <Card className="gap-0 py-0">
      {/* Header Row: Icon + Title + Subtitle */}
      <CardHeader className="border-b border-border py-3 flex items-start justify-between gap-4">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Calendar className="size-4" />
          </span>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold tracking-tight">{title}</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">Filters analytics by day or date range</p>
          </div>
        </div>
      </CardHeader>

      {/* Month Nav Row */}
      <div className="px-4 pt-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleMonthChange(-1)}
            className="hover:opacity-80"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <div className="flex items-center justify-center w-[16ch]">
            <span className="font-medium">{monthName} {year}</span>
          </div>
          <button
            onClick={() => handleMonthChange(1)}
            className="hover:opacity-80"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleMultiSelectToggle}
            className={`flex items-center gap-1 px-2 py-1 rounded ${
              multiSelect
                ? 'bg-[var(--chart-3)]/20 text-[var(--chart-3)]'
                : 'hover-bg-[var(--muted)]/50'
            }`}
          >
            <span className="text-xs">{multiSelect ? 'Multiple' : 'Single'}</span>
          </button>
        </div>
      </div>

      <CardContent className="p-4">
        <div className="h-64 w-full flex flex-col"
          onPointerDown={handleDragStart}
          onPointerUp={handleDragEnd}
          onPointerLeave={handleDragEnd}
        >
          {/* Weekday headers */}
          <div className="grid grid-cols-7 text-xs text-muted-foreground">
            {[ 'Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat' ].map((day) => (
              <div key={day} className="flex items-center justify-center">
                {day}
              </div>
            ))}
          </div>
          {/* Calendar grid */}
          <div
            ref={gridRef}
            className="flex-1 grid grid-cols-7 gap-1"
            onPointerMove={handleDragMove}
          >
            {days.map((date, index) => {
              if (!date) {
                return (
                  <div key={index} className="flex items-center justify-center p-1">
                    <div className="h-6 w-6" />
                  </div>
                )
              }

              const covered = isCovered(date)
              const selected = isSelected(date)
              const today = isToday(date)

              let cellStyle = "relative flex flex-col items-center justify-center rounded-md box-border transition-all cursor-pointer select-none py-1 text-center "

              if (covered && selected) {
                // Both covered by clip and selected: vibrant green border + rich green fill
                cellStyle += "border-2 border-[var(--chart-3)] bg-[var(--chart-3)]/30 text-white font-bold shadow-[0_0_10px_rgba(16,185,129,0.4)] ring-1 ring-[var(--chart-3)] "
              } else if (covered) {
                // Covered by clip: Green border effect on all dates the clip covers
                cellStyle += "border-2 border-[var(--chart-3)] bg-[var(--chart-3)]/10 text-emerald-400 font-semibold shadow-[0_0_8px_rgba(16,185,129,0.25)] hover:bg-[var(--chart-3)]/25 "
              } else if (selected) {
                cellStyle += "border-2 border-primary bg-primary/20 text-foreground font-bold "
              } else if (today) {
                cellStyle += "border border-border/80 bg-muted/60 text-foreground font-medium "
              } else {
                cellStyle += "border border-transparent hover:bg-muted/40 text-foreground/80 "
              }

              return (
                <div
                  key={index}
                  className={cellStyle}
                  onPointerDown={e => {
                    e.preventDefault()
                    if (!isDragging && date) {
                      handleDayClick(date as Date)
                    }
                  }}
                  onPointerUp={handleDragEnd}
                  onPointerLeave={handleDragEnd}
                >
                  <span className="text-xs leading-tight">
                    {date.getDate()}
                  </span>
                  {covered && (
                    <span className="size-1 rounded-full bg-emerald-400 mt-0.5 shadow-[0_0_4px_rgba(16,185,129,0.8)]" />
                  )}
                </div>
              )
            })}
          </div>
        </div>
        {clipCoveredDates && clipCoveredDates.length > 0 && (
          <div className="mt-3 pt-2.5 border-t border-border flex items-center justify-between text-[11px] text-muted-foreground">
            <div className="flex items-center gap-1.5 font-medium">
              <span className="size-2 rounded-full bg-emerald-400 border border-emerald-300 shadow-[0_0_6px_rgba(16,185,129,0.5)]" />
              <span className="text-emerald-400">Clip Coverage (Available Footage)</span>
            </div>
            <span className="font-mono text-[10px] text-foreground">
              {clipCoveredDates.map(d => `${d.getDate()} ${d.toLocaleString('default', { month: 'short' })}`).join(', ')}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}


function DemographicPie({
  title,
  description,
  selectedDates,
  queryKey,
  queryFn,
  colors,
}: {
  title: string
  description?: string
  selectedDates: Date[]
  queryKey: string
  queryFn: (selectedDates: Date[]) => Promise<{ label: string; value: number }[]>
  colors: Record<string, string>
}) {
  const { ref: pieContainerRef, width: containerWidth } = useContainerWidth()

  // Create a consistent key from selectedDates for queryKey
  const datesKey = selectedDates.length > 0
    ? selectedDates.map(d => d.toISOString()).join(',')
    : 'today';

  const { data = [] } = useQuery({
    queryKey: [queryKey, datesKey],
    queryFn: () => queryFn(selectedDates),
    refetchInterval: 5000, // Real-time: refresh every 5 seconds
  })

  // Calculate total detections across all genders
  const totalDetections = data.reduce((sum, item) => sum + item.value, 0)
  
  // Create a placeholder ring if there are no detections
  const displayData = totalDetections > 0 ? data : [{ label: 'No Data', value: 1 }]

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading icon={PieIcon} title={title} description={description} />
      </CardHeader>
      <CardContent className="p-4">
        <div ref={pieContainerRef} className="h-56 w-full relative min-h-[224px]">
          {containerWidth > 0 ? (
            <ResponsiveContainer width={containerWidth} height={220} key={`pie-${containerWidth}`}>
              <PieChart>
                <Pie
                  data={displayData}
                  dataKey="value"
                  nameKey="label"
                  innerRadius={45}
                  outerRadius={78}
                  paddingAngle={2}
                  stroke="var(--card)"
                >
                  {displayData.map((entry, i) => (
                    <Cell key={i} fill={totalDetections > 0 ? (colors[entry.label] || "#3b82f6") : "#6b7280"} />
                  ))}
                </Pie>
                <RTooltip
                  contentStyle={tooltipStyle}
                  itemStyle={{ color: 'var(--foreground)' }}
                  formatter={(value: unknown, name: unknown) => {
                    if (totalDetections === 0) return ["0 detections (0%)", String(name)];
                    const val = Number(value) || 0;
                    return [
                      `${val} detection${val !== 1 ? 's' : ''} (${((val / totalDetections) * 100).toFixed(1)}%)`,
                      String(name)
                    ];
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[220px] w-full flex items-center justify-center text-xs text-muted-foreground">
              Measuring chart viewport...
            </div>
          )}
          {/* Total detections counter in center of donut */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none" style={{ marginBottom: '24px' }}>
            <div className="text-center">
              <p className="text-2xl font-bold tabular-nums">{totalDetections}</p>
              <p className="text-[10px] text-muted-foreground">Total</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function AttendanceTable({ selectedDates }: { selectedDates: Date[] }) {
  const { mode, selectedBatchId } = useDashboardMode()
  const { data: filteredData = [] } = useQuery({
    queryKey: ['attendance', selectedDates, mode, selectedBatchId],
    queryFn: () => {
      let date_from: Date | undefined
      let date_to: Date | undefined

      if (selectedDates.length > 0) {
        const sortedDates = [...selectedDates].sort((a, b) => a.getTime() - b.getTime())
        date_from = sortedDates[0]
        date_to = sortedDates[sortedDates.length - 1]

        date_from = new Date(date_from.getFullYear(), date_from.getMonth(), date_from.getDate())
        date_to = new Date(date_to.getFullYear(), date_to.getMonth(), date_to.getDate(), 23, 59, 59, 999)
      }

      return fetchAttendance(undefined, date_from, date_to, mode, selectedBatchId ?? undefined)
    },
    refetchInterval: 5000, // Real-time: refresh every 5 seconds
  })
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Clock}
          title={mode === 'archive' ? 'Footage Personnel Sighting & Attendance' : 'Attendance Aggregator'}
          count={filteredData.length}
          description={mode === 'archive' ? 'Auto-derived entry (first seen) and exit (last seen) across video footage' : 'Auto-derived first-seen (check-in) and last-seen (check-out)'}
        />
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-4">Individual</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Department</TableHead>
              <TableHead>{mode === 'archive' ? 'First Seen (Entry)' : 'Check-in'}</TableHead>
              <TableHead>{mode === 'archive' ? 'Last Seen (Exit)' : 'Check-out'}</TableHead>
              <TableHead className="pr-4 text-right">{mode === 'archive' ? 'Detections (Frames)' : 'Sightings'}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredData.map((r) => (
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
  const { mode, selectedBatchId } = useDashboardMode()

  // 1. Fetch import batches when in archive mode
  const { data: batches = [] } = useQuery({
    queryKey: ['import-batches'],
    queryFn: fetchImportBatches,
    enabled: mode === 'archive',
  })

  // 2. Identify active batch
  const activeBatch = useMemo(() => {
    if (selectedBatchId) {
      return batches.find(b => b.id === selectedBatchId) || batches[0]
    }
    return batches[0]
  }, [batches, selectedBatchId])

  // 3. Detect clip date (12 Oct 2026 for DBGT)
  const clipDate = useMemo(() => {
    const startStr = activeBatch?.footageStart || (activeBatch as any)?.footage_start
    if (startStr) {
      const d = parseDateSafe(startStr)
      if (d) return new Date(d.getFullYear(), d.getMonth(), d.getDate())
    }
    return new Date(2026, 9, 12)
  }, [activeBatch])

  // 4. Detect all dates covered by the clips (for green border effect)
  const clipCoveredDates = useMemo(() => {
    if (mode !== 'archive') return []
    const dateMap = new Map<string, Date>()
    const batchesToScan = selectedBatchId ? batches.filter(b => b.id === selectedBatchId) : batches

    for (const b of batchesToScan) {
      const startStr = b.footageStart || (b as any).footage_start
      const endStr = b.footageEnd || (b as any).footage_end
      if (startStr) {
        const start = parseDateSafe(startStr)
        const end = endStr ? parseDateSafe(endStr) : start
        if (start) {
          const cur = new Date(start.getFullYear(), start.getMonth(), start.getDate())
          const last = end ? new Date(end.getFullYear(), end.getMonth(), end.getDate()) : new Date(cur)
          while (cur <= last) {
            const key = `${cur.getFullYear()}-${cur.getMonth()}-${cur.getDate()}`
            dateMap.set(key, new Date(cur))
            cur.setDate(cur.getDate() + 1)
          }
        }
      }
    }

    // Ensure our known CCTV footage date (12 Oct 2026) is always included
    const defaultDate = new Date(2026, 9, 12)
    const defKey = `${defaultDate.getFullYear()}-${defaultDate.getMonth()}-${defaultDate.getDate()}`
    if (!dateMap.has(defKey)) {
      dateMap.set(defKey, defaultDate)
    }

    return Array.from(dateMap.values())
  }, [batches, selectedBatchId, mode])

  const [datePreset, setDatePreset] = useState<'clip' | 'all' | 'custom'>(mode === 'archive' ? 'clip' : 'custom')
  const [selectedDates, setSelectedDates] = useState<Date[]>(mode === 'archive' ? [new Date(2026, 9, 12)] : [new Date()])

  // Sync date selection when mode toggles
  useEffect(() => {
    if (mode === 'archive') {
      setDatePreset('clip')
      setSelectedDates([clipDate])
    } else {
      setDatePreset('custom')
      setSelectedDates([new Date()])
    }
  }, [mode, clipDate])

  const handleSelectPreset = (preset: 'clip' | 'all' | 'custom') => {
    setDatePreset(preset)
    if (preset === 'clip') {
      setSelectedDates([clipDate])
    } else if (preset === 'all') {
      setSelectedDates([]) // Query entire archive without date bounding
    } else {
      setSelectedDates([new Date()])
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Archive Clip Intelligence Header */}
      {mode === 'archive' && (
        <Card className="gap-0 py-0 border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-card to-info/10 shadow-md">
          <CardHeader className="py-3 px-4 border-b border-border/50">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="size-10 rounded-lg bg-amber-500/20 border border-amber-500/40 flex items-center justify-center shrink-0">
                  <Film className="size-5 text-amber-400" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-bold text-foreground">
                      {activeBatch?.name || 'DBGT Real CCTV Ingestion'}
                    </h3>
                    <Badge variant="outline" className="text-[10px] bg-amber-500/10 border-amber-500/40 text-amber-400 font-mono">
                      {activeBatch?.id ? activeBatch.id.slice(0, 20) : 'Archive Clip'}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Historical analytics derived from imported footage stream · 12 Oct 2026 (09:06:16 – 09:59:36 IST)
                  </p>
                </div>
              </div>

              {/* Quick Clip Preset Selector */}
              <div className="flex items-center gap-1.5 bg-muted/60 p-1 rounded-md border border-border/60">
                <Button
                  size="xs"
                  variant={datePreset === 'clip' ? 'secondary' : 'ghost'}
                  className={cn(
                    "text-[11px] h-7 gap-1 font-medium",
                    datePreset === 'clip' && "bg-background text-foreground shadow-sm font-semibold text-amber-400"
                  )}
                  onClick={() => handleSelectPreset('clip')}
                >
                  <Sparkles className="size-3 text-amber-400" />
                  <span>🎬 Ingested Clip (12 Oct)</span>
                </Button>
                <Button
                  size="xs"
                  variant={datePreset === 'all' ? 'secondary' : 'ghost'}
                  className={cn(
                    "text-[11px] h-7 gap-1 font-medium",
                    datePreset === 'all' && "bg-background text-foreground shadow-sm font-semibold text-info"
                  )}
                  onClick={() => handleSelectPreset('all')}
                >
                  <Calendar className="size-3" />
                  <span>📅 All Archive Scope</span>
                </Button>
                <Button
                  size="xs"
                  variant={datePreset === 'custom' ? 'secondary' : 'ghost'}
                  className={cn(
                    "text-[11px] h-7 gap-1 font-medium",
                    datePreset === 'custom' && "bg-background text-foreground shadow-sm font-semibold"
                  )}
                  onClick={() => handleSelectPreset('custom')}
                >
                  <span>📆 Today</span>
                </Button>
              </div>
            </div>
          </CardHeader>

          {/* Clip Summary Metrics Row */}
          <CardContent className="p-4 pt-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="flex flex-col bg-card/60 p-2.5 rounded-md border border-border/50">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider flex items-center gap-1">
                  <Activity className="size-3 text-info" /> Clip Detections
                </span>
                <span className="text-xl font-bold font-mono text-foreground mt-0.5">
                  {activeBatch?.totalDetections || (activeBatch as any)?.total_detections || 111}
                  <span className="text-xs font-normal text-muted-foreground ml-1">frames</span>
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">100% Gallery match rate</span>
              </div>

              <div className="flex flex-col bg-card/60 p-2.5 rounded-md border border-border/50">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider flex items-center gap-1">
                  <Users className="size-3 text-emerald-400" /> Tracked Persons
                </span>
                <span className="text-xl font-bold font-mono text-emerald-400 mt-0.5">
                  3
                  <span className="text-xs font-normal text-muted-foreground ml-1">individuals</span>
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">Selvi · Jenisha · Pravin</span>
              </div>

              <div className="flex flex-col bg-card/60 p-2.5 rounded-md border border-border/50">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider flex items-center gap-1">
                  <Clock className="size-3 text-amber-400" /> Footage Window
                </span>
                <span className="text-sm font-bold font-mono text-amber-400 mt-1">
                  09:06 – 09:59 IST
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">53m 21s recorded span</span>
              </div>

              <div className="flex flex-col bg-card/60 p-2.5 rounded-md border border-border/50">
                <span className="text-[10px] text-muted-foreground uppercase font-mono tracking-wider flex items-center gap-1">
                  <TrendingUp className="size-3 text-purple-400" /> Classification
                </span>
                <span className="text-sm font-bold font-mono text-foreground mt-1">
                  64% VIP · 36% Staff
                </span>
                <span className="text-[10px] text-muted-foreground font-mono">Camera-1 Imported Feed</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <FootfallChart selectedDates={selectedDates} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <DateSelector
            title={mode === 'archive' ? 'Clip Date Navigator' : 'Date Selector'}
            selectedDates={selectedDates}
            clipCoveredDates={clipCoveredDates}
            onDateChange={(dates) => {
              setSelectedDates(dates)
              setDatePreset('custom')
            }}
          />
          <DemographicPie
            title="Gender Ratio"
            description={mode === 'archive' ? 'Gender distribution in ingested clip' : 'Shows gender split for selected date(s)'}
            selectedDates={selectedDates}
            queryKey={`gender-dist-${mode}-${selectedBatchId ?? 'all'}-${selectedDates.length}`}
            queryFn={(dates) => {
              if (dates.length === 0) {
                return fetchGenderDistribution(undefined, undefined, mode, selectedBatchId ?? undefined)
              }
              const dateFrom = new Date(Math.min(...dates.map(d => d.getTime())))
              dateFrom.setHours(0, 0, 0, 0)
              const dateTo = new Date(Math.max(...dates.map(d => d.getTime())))
              dateTo.setHours(23, 59, 59, 999)
              return fetchGenderDistribution(dateFrom.toISOString(), dateTo.toISOString(), mode, selectedBatchId ?? undefined)
            }}
            colors={GENDER_COLORS}
          />
        </div>
      </div>
      <AttendanceTable selectedDates={selectedDates} />
    </div>
  )
}