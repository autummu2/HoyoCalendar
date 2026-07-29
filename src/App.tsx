import { useState, useCallback, useMemo } from 'react'
import { useTheme } from './hooks/useTheme'
import { useEvents } from './hooks/useEvents'
import { buildCalendarGrid, getToday, parseDate, formatDate, isDateInRange } from './lib/date-utils'
import { MONTH_LABELS } from './lib/constants'
import { Header, formatWeekLabel, formatDayLabel } from './components/layout/Header'
import { CalendarGrid } from './components/calendar/CalendarGrid'
import { DayView } from './components/calendar/DayView'
import { EventDetail } from './components/event/EventDetail'
import { GameFilter } from './components/filter/GameFilter'
import { TypeFilter } from './components/filter/TypeFilter'
import type { Game, EventTypeId } from './types/events'

type ViewMode = 'month' | 'week' | 'day'

export default function App() {
  // ===== 主题 =====
  const { theme, toggleTheme } = useTheme()

  // ===== 日期与视图状态 =====
  const today = getToday()
  const [viewMode, setViewMode] = useState<ViewMode>('month')
  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear())
  const [currentMonth, setCurrentMonth] = useState(() => new Date().getMonth() + 1)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [highlightedEventId, setHighlightedEventId] = useState<string | null>(null)

  // ===== 筛选状态 =====
  const [gameFilter, setGameFilter] = useState<Game[]>([])
  const [typeFilter, setTypeFilter] = useState<EventTypeId[]>([])

  // ===== 活动数据 =====
  const { events, loading, error } = useEvents()

  // ===== 筛选后的活动 =====
  const filteredEvents = useMemo(() => {
    return events.filter((e) => {
      if (gameFilter.length > 0 && !gameFilter.includes(e.game)) return false
      if (typeFilter.length > 0 && !typeFilter.includes(e.type)) return false
      return true
    })
  }, [events, gameFilter, typeFilter])

  // ===== 日历网格 =====
  const fullGrid = buildCalendarGrid(currentYear, currentMonth)

  // 周视图：只显示包含 selectedDate 的那一周
  const displayWeeks = useMemo(() => {
    if (viewMode !== 'week' || !selectedDate) return fullGrid
    const wi = fullGrid.findIndex((w) => w.some((d) => d.date === selectedDate))
    return wi >= 0 ? [fullGrid[wi]] : fullGrid
  }, [viewMode, fullGrid, selectedDate])

  // ===== 导航标签 =====
  const navLabel = useMemo(() => {
    switch (viewMode) {
      case 'month':
        return `${currentYear}年 ${MONTH_LABELS[currentMonth - 1]}`
      case 'week': {
        const focusDate = selectedDate ?? today
        const wi = fullGrid.findIndex((w) => w.some((d) => d.date === focusDate))
        if (wi >= 0) {
          return formatWeekLabel(fullGrid[wi][0].date, fullGrid[wi][6].date)
        }
        return ''
      }
      case 'day':
        return formatDayLabel(selectedDate ?? today)
    }
  }, [viewMode, currentYear, currentMonth, selectedDate, today, fullGrid])

  // ===== 导航逻辑（按视图模式） =====
  const syncMonthToDate = useCallback((dateStr: string) => {
    const d = parseDate(dateStr)
    setCurrentYear(d.getFullYear())
    setCurrentMonth(d.getMonth() + 1)
  }, [])

  const goPrev = useCallback(() => {
    if (viewMode === 'month') {
      if (currentMonth === 1) { setCurrentYear((y) => y - 1); setCurrentMonth(12) }
      else { setCurrentMonth((m) => m - 1) }
    } else if (viewMode === 'week') {
      const base = selectedDate ?? today
      const d = parseDate(base)
      d.setDate(d.getDate() - 7)
      const newDate = formatDate(d)
      setSelectedDate(newDate)
      syncMonthToDate(newDate)
    } else {
      const base = selectedDate ?? today
      const d = parseDate(base)
      d.setDate(d.getDate() - 1)
      const newDate = formatDate(d)
      setSelectedDate(newDate)
      syncMonthToDate(newDate)
    }
  }, [viewMode, currentMonth, selectedDate, today, syncMonthToDate])

  const goNext = useCallback(() => {
    if (viewMode === 'month') {
      if (currentMonth === 12) { setCurrentYear((y) => y + 1); setCurrentMonth(1) }
      else { setCurrentMonth((m) => m + 1) }
    } else if (viewMode === 'week') {
      const base = selectedDate ?? today
      const d = parseDate(base)
      d.setDate(d.getDate() + 7)
      const newDate = formatDate(d)
      setSelectedDate(newDate)
      syncMonthToDate(newDate)
    } else {
      const base = selectedDate ?? today
      const d = parseDate(base)
      d.setDate(d.getDate() + 1)
      const newDate = formatDate(d)
      setSelectedDate(newDate)
      syncMonthToDate(newDate)
    }
  }, [viewMode, currentMonth, selectedDate, today, syncMonthToDate])

  const goToday = useCallback(() => {
    const now = new Date()
    setCurrentYear(now.getFullYear())
    setCurrentMonth(now.getMonth() + 1)
    setSelectedDate(today)
  }, [today])

  // ===== 选中日期的活动 =====
  const selectedEvents = selectedDate
    ? filteredEvents.filter((e) => isDateInRange(selectedDate, e.start_date, e.end_date))
    : []

  const handleSelectDate = useCallback((date: string) => {
    setSelectedDate(date)
    setHighlightedEventId(null)
  }, [])

  const handleSelectEvent = useCallback((date: string, eventId: string) => {
    setSelectedDate(date)
    setHighlightedEventId(eventId)
  }, [])

  // ===== 错误状态 =====
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen" style={{ color: 'var(--text-secondary)' }}>
        <p>加载活动数据失败：{error}</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        viewMode={viewMode}
        onChangeView={setViewMode}
        navLabel={navLabel}
        onPrev={goPrev}
        onNext={goNext}
        onToday={goToday}
      />

      {/* ===== 筛选栏 ===== */}
      <div
        className="flex items-center gap-4 px-6 py-2 border-b flex-wrap"
        style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-surface)' }}
      >
        <GameFilter selected={gameFilter} onChange={setGameFilter} />
        <TypeFilter selected={typeFilter} onChange={setTypeFilter} />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* 主内容区 */}
        <div className="flex-1 flex flex-col overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center flex-1" style={{ color: 'var(--text-muted)' }}>
              <p>加载中...</p>
            </div>
          ) : viewMode === 'day' ? (
            <DayView
              date={selectedDate ?? today}
              events={selectedEvents}
              highlightedEventId={highlightedEventId}
              onSelectEvent={(id) => setHighlightedEventId(id)}
            />
          ) : (
            <CalendarGrid
              weeks={displayWeeks}
              events={filteredEvents}
              selectedDate={selectedDate}
              onSelectDate={handleSelectDate}
              onSelectEvent={handleSelectEvent}
            />
          )}
        </div>

        {/* 活动详情侧栏（月/周视图时显示） */}
        {viewMode !== 'day' && selectedDate && (
          <EventDetail
            events={selectedEvents}
            date={selectedDate}
            highlightedEventId={highlightedEventId}
            onClose={() => { setSelectedDate(null); setHighlightedEventId(null) }}
          />
        )}
      </div>
    </div>
  )
}
