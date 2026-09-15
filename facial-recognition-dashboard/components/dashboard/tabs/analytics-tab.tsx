'use client'

import { useState, useRef } from 'react'
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
  fetchFaceLogs,
  fetchFootfall,
  fetchGenderDistribution
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
  Calendar,
} from 'lucide-react'

const GENDER_COLORS = ['var(--chart-4)', 'var(--chart-1)', 'var(--muted-foreground)']

// Helper function to fetch gender distribution filtered by date
const fetchGenderDistributionByDate = async (selectedDates: Date[]): Promise<{ label: string; value: number }[]> => {
  // If no dates selected, default to today
  const filterDates = selectedDates.length > 0 ? selectedDates : [new Date()]

  try {
    // Fetch face logs (we'll get a reasonable limit to cover the date range)
    const faceLogs = await fetchFaceLogs(1000) // Get more logs to increase chance of matching dates

    // Filter logs by selected dates
    const filteredLogs = faceLogs.filter(log => {
      const logDate = parseTimestampToDate(log.timestamp)
      return filterDates.some(filterDate => isSameDay(logDate, filterDate))
    })

    // Aggregate by gender
    const genderCounts = {
      male: 0,
      female: 0,
      unknown: 0
    }

    filteredLogs.forEach(log => {
      if (log.gender === 'male') {
        genderCounts.male++
      } else if (log.gender === 'female') {
        genderCounts.female++
      } else {
        genderCounts.unknown++
      }
    })

    // Convert to the format expected by DemographicPie
    return [
      { label: 'Male', value: genderCounts.male },
      { label: 'Female', value: genderCounts.female },
      { label: 'Unknown', value: genderCounts.unknown }
    ]
  } catch (error) {
    // Return empty data on error
    return [
      { label: 'Male', value: 0 },
      { label: 'Female', value: 0 },
      { label: 'Unknown', value: 0 }
    ]
  }
}

const tooltipStyle = {
  backgroundColor: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: '8px',
  fontSize: '12px',
  color: 'var(--popover-foreground)',
}

function FootfallChart({ selectedDates }: { selectedDates: Date[] }) {
  const { data = [] } = useQuery({
    queryKey: ['footfall', selectedDates],
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

        // Set to end of day (23:59:59.999999) for date_to
        date_to = new Date(date_to.getFullYear(), date_to.getMonth(), date_to.getDate(), 23, 59, 59, 999999)
      }

      return fetchFootfall(undefined, date_from, date_to)
    }
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
            <BarChart data={allHours} barCategoryGap={4}>
              <XAxis
                dataKey="hour"
                tick={{
                  fill: 'var(--muted-foreground)',
                  fontSize: 11,
                  // Format tick labels to show just hour number (00, 01, 02, ..., 23)
                  // instead of "00:00", "01:00", etc.
                  formatter: (value) => {
                    // Value should be in "HH" format (e.g., "00", "01", etc.)
                    // Return as-is for consistent display
                    if (typeof value === 'string') {
                      return value;
                    }
                    return String(value).padStart(2, '0');
                  }
                }}
                // Ensure all ticks are shown (prevent auto-hiding)
                tickCount={24}
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

function DateSelector({
  title = "Date Selector",
  onDateChange,
}: {
  title?: string
  onDateChange: (dates: Date[]) => void
}) {
  const [currentDate, setCurrentDate] = useState(new Date())
  const [selectedDates, setSelectedDates] = useState<Date[]>([])
  const [multiSelect, setMultiSelect] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStartCell, setDragStartCell] = useState<number | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const monthName = currentDate.toLocaleString('default', { month: 'long' })
  const year = currentDate.getFullYear()
  const firstDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1)
  const lastDayOfMonth = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0)
  const startingDayIndex = firstDayOfMonth.getDay() // 0 for Sunday, 1 for Monday, etc.
  const daysInMonth = lastDayOfMonth.getDate()

  // Generate days for the calendar grid (5 weeks * 7 days = 35 days)
  const days = []
  // Add empty cells for the days before the first day of the month
  for (let i = 0; i < startingDayIndex; i++) {
    days.push(null)
  }
  // Add days of the month
  for (let day = 1; day <= daysInMonth; day++) {
    days.push(new Date(currentDate.getFullYear(), currentDate.getMonth(), day))
  }
  // Fill the rest with null to complete 35 days (5 rows * 7 columns)
  while (days.length < 35) {
    days.push(null)
  }

  const isSameDay = (date1: Date, date2: Date) =>
    date1.getDate() === date2.getDate() &&
    date1.getMonth() === date2.getMonth() &&
    date1.getFullYear() === date2.getFullYear()

  const isToday = (date: Date) => isSameDay(date, new Date())

  const isSelected = (date: Date) =>
    selectedDates.some((d) => isSameDay(d, date))

  const handleDayClick = (date: Date) => {
    if (!date) return
    if (multiSelect && !isDragging) {
      // Only toggle on click if not dragging (to avoid toggling on drag end)
      const isAlreadySelected = isSelected(date)
      const updatedDates = isAlreadySelected
        ? selectedDates.filter((d) => !isSameDay(d, date))
        : [...selectedDates, date]
      setSelectedDates(updatedDates)
      onDateChange(updatedDates)
    } else if (!multiSelect) {
      // Single select mode: always set to the clicked date
      setSelectedDates([date])
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
          setSelectedDates(newSelectedDates)
          onDateChange(newSelectedDates)
        } else if (clickedDate) {
          const newSelectedDates = selectedDates.filter(d => !isSameDay(d, clickedDate))
          setSelectedDates(newSelectedDates)
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
      !days.some((d, idx) => idx >= start && idx <= end && isSameDay(d, date))
    )

    // Combine and deduplicate
    const allSelected = [...preselectedDates, ...newSelectedDates]
    const deduplicated: Date[] = []
    allSelected.forEach(date => {
      if (!deduplicated.some(d => isSameDay(d, date))) {
        deduplicated.push(date)
      }
    })

    setSelectedDates(deduplicated)
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
    const cellHeight = rect.height / 5

    // Adjust for the header row (first row is weekdays)
    const xInGrid = clientX - rect.left
    const yInGrid = clientY - rect.top

    // Skip if outside grid
    if (xInGrid < 0 || xInGrid > rect.width || yInGrid < 0 || yInGrid > rect.height) {
      return null
    }

    // Calculate column and row (0-indexed)
    const col = Math.floor(xInGrid / cellWidth)
    const row = Math.floor(yInGrid / cellHeight) - 1 // -1 to skip header row

    // Skip if in header row or outside grid
    if (row < 0 || row >= 5 || col < 0 || col >= 7) {
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
      setSelectedDates([today])
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
        <div className="h-56 w-full flex flex-col"
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
            {days.map((date, index) => (
              <div
                key={index}
                className={`flex items-center justify-center rounded box-border border-[1px] ${
                  date && isToday(date) ? 'bg-[var(--chart-3)] text-black' : ''
                } ${date && isSelected(date) ? 'border-[var(--chart-3)]' : 'border-transparent'} ${date && !isToday(date) && !isSelected(date) ? 'hover:bg-[var(--muted)]/50' : ''} ` }
                onPointerDown={e => {
                  e.preventDefault()
                  // Don't start drag here - handled by container
                  // Just toggle the cell if not dragging
                  if (!isDragging) {
                    handleDayClick(date)
                  }
                }}
                onPointerOver={() => {
                  // Hover effect for non-dragging
                  if (!isDragging && !multiSelect && date && !isToday(date) && !isSelected(date)) {
                    // Handled by hover class in className
                  }
                }}
                onPointerUp={handleDragEnd}
                onPointerLeave={handleDragEnd}
              >
                {date ? (
                  <div className="text-sm font-medium">
                    {date.getDate()}
                  </div>
                ) : (
                  <div className="h-4 w-4" />
                )}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// Helper function to check if two dates are the same day
function isSameDay(date1: Date, date2: Date): boolean {
  return date1.getDate() === date2.getDate() &&
         date1.getMonth() === date2.getMonth() &&
         date1.getFullYear() === date2.getFullYear()
}

// Helper function to parse timestamp string to Date object, handling local time format
function parseTimestampToDate(timestamp: string): Date {
  // Try parsing as ISO format first (with T and/or Z)
  let date = new Date(timestamp)

  // If that gives a valid date and the year is not 1970 (indicating time-only string),
  // return it directly
  if (!isNaN(date.getTime()) && date.getFullYear() !== 1970) {
    return date
  }

  // If parsing failed or gave year 1970, try to parse as "YYYY-MM-DD HH:MM:SS" format
  // This handles cases where timestamp is in local time without timezone designator
  const match = timestamp.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})$/)
  if (match) {
    const [, year, month, day, hour, minute, second] = match
    // Month is 0-indexed in JavaScript Date
    return new Date(parseInt(year, 10), parseInt(month, 10) - 1, parseInt(day, 10),
                    parseInt(hour, 10), parseInt(minute, 10), parseInt(second, 10))
  }

  // If that also fails, try to parse as "YYYY-MM-DDTHH:MM:SS" format
  const match2 = timestamp.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/)
  if (match2) {
    const [, year, month, day, hour, minute, second] = match2
    // Month is 0-indexed in JavaScript Date
    return new Date(parseInt(year, 10), parseInt(month, 10) - 1, parseInt(day, 10),
                    parseInt(hour, 10), parseInt(minute, 10), parseInt(second, 10))
  }

  // Fallback to returning an invalid date if all parsing attempts fail
  return new Date(NaN)
}

function DemographicPie({
  title,
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
  colors: string[]
}) {
  // Create a consistent key from selectedDates for queryKey
  const datesKey = selectedDates.length > 0
    ? selectedDates.map(d => d.toISOString()).join(',')
    : 'today';

  const { data = [] } = useQuery({
    queryKey: [queryKey, datesKey],
    queryFn: () => queryFn(selectedDates)
  })
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading icon={PieIcon} title={title} description={description} />
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

function AttendanceTable({ selectedDates }: { selectedDates: Date[] }) {
  const { data = [] } = useQuery({
    queryKey: ['attendance'],
    queryFn: () => fetchAttendance(),
  })

  // Determine which dates to filter by: if none selected, use today; otherwise use selected dates
  const filterDates = selectedDates.length > 0 ? selectedDates : [new Date()]

  
  // Filter attendance data by selected dates
  const filteredData = data.filter(record => {
    // Check if checkIn or checkOut date matches any selected date
    const checkInDate = new Date(record.checkIn)
    const checkOutDate = new Date(record.checkOut)

    const checkInMatch = filterDates.some(filterDate => {
      const isMatch = isSameDay(filterDate, checkInDate)
      if (isMatch) {
      }
      return isMatch
    })

    const checkOutMatch = filterDates.some(filterDate => {
      const isMatch = isSameDay(filterDate, checkOutDate)
      if (isMatch) {
      }
      return isMatch
    })

    const result = checkInMatch || checkOutMatch
    return result
  })

  
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="border-b border-border py-3">
        <SectionHeading
          icon={Clock}
          title="Attendance Aggregator"
          count={filteredData.length}
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
  const [selectedDates, setSelectedDates] = useState<Date[]>([])

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <FootfallChart selectedDates={selectedDates} />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <DateSelector
            title="Date Selector"
            onDateChange={setSelectedDates}
          />
          <DemographicPie
            title="Gender Ratio"
            description="Shows gender split for selected date(s)"
            selectedDates={selectedDates}
            queryKey="gender-dist"
            queryFn={(selectedDates) => fetchGenderDistributionByDate(selectedDates)}
            colors={GENDER_COLORS}
          />
        </div>
      </div>
      <AttendanceTable selectedDates={selectedDates} />
    </div>
  )
}