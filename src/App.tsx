import { useState, useCallback } from 'react'
import { useTheme } from './hooks/useTheme'
import { useEvents } from './hooks/useEvents'
import { buildCalendarGrid, getToday } from './lib/date-utils'
import { isDateInRange } from './lib/date-utils'
import { Header } from './components/layout/Header'
import { CalendarGrid } from './components/calendar/CalendarGrid'
import { EventDetail } from './components/event/EventDetail'

export default function App() {
  // ===== 主题 =====
  const { theme, toggleTheme } = useTheme()

  // ===== 日期状态 =====
  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear())
  const [currentMonth, setCurrentMonth] = useState(() => new Date().getMonth() + 1)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  // ===== 活动数据 =====
  const { events, loading, error } = useEvents()

  // ===== 日历网格 =====
  const weeks = buildCalendarGrid(currentYear, currentMonth)

  // ===== 导航 =====
  const goToPrevMonth = useCallback(() => {
    if (currentMonth === 1) {
      setCurrentYear((y) => y - 1)
      setCurrentMonth(12)
    } else {
      setCurrentMonth((m) => m - 1)
    }
  }, [currentMonth])

  const goToNextMonth = useCallback(() => {
    if (currentMonth === 12) {
      setCurrentYear((y) => y + 1)
      setCurrentMonth(1)
    } else {
      setCurrentMonth((m) => m + 1)
    }
  }, [currentMonth])

  const goToToday = useCallback(() => {
    const now = new Date()
    setCurrentYear(now.getFullYear())
    setCurrentMonth(now.getMonth() + 1)
    setSelectedDate(getToday())
  }, [])

  // ===== 选中日期的活动 =====
  const selectedEvents = selectedDate
    ? events.filter((e) => isDateInRange(selectedDate, e.start_date, e.end_date))
    : []

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
        year={currentYear}
        month={currentMonth}
        onPrevMonth={goToPrevMonth}
        onNextMonth={goToNextMonth}
        onToday={goToToday}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* 日历主体 */}
        <div className="flex-1 flex flex-col overflow-auto">
          {loading ? (
            <div className="flex items-center justify-center flex-1" style={{ color: 'var(--text-muted)' }}>
              <p>加载中...</p>
            </div>
          ) : (
            <CalendarGrid
              weeks={weeks}
              events={events}
              selectedDate={selectedDate}
              onSelectDate={setSelectedDate}
            />
          )}
        </div>

        {/* 活动详情侧栏 */}
        {selectedDate && (
          <EventDetail
            events={selectedEvents}
            date={selectedDate}
            onClose={() => setSelectedDate(null)}
          />
        )}
      </div>
    </div>
  )
}
