import type { CalendarDay } from '../../lib/date-utils'
import type { GameEvent } from '../../types/events'
import { WEEKDAY_LABELS } from '../../lib/constants'
import { isDateInRange } from '../../lib/date-utils'

interface CalendarGridProps {
  weeks: CalendarDay[][]
  events: GameEvent[]
  selectedDate: string | null
  onSelectDate: (date: string) => void
}

/**
 * 日历月视图网格组件
 * 6行 × 7列标准日历布局，基于 CSS Grid
 */
export function CalendarGrid({ weeks, events, selectedDate, onSelectDate }: CalendarGridProps) {
  // 获取某个日期对应的活动列表（用于在格子内渲染色条）
  const getEventsForDate = (date: string): GameEvent[] => {
    return events.filter((e) => isDateInRange(date, e.start_date, e.end_date))
  }

  return (
    <div className="flex-1 flex flex-col px-6 pb-6">
      {/* 星期头 */}
      <div className="grid grid-cols-7 mb-1">
        {WEEKDAY_LABELS.map((label, i) => (
          <div
            key={i}
            className="text-center text-sm font-medium py-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            {label}
          </div>
        ))}
      </div>

      {/* 日期格子 */}
      <div className="grid grid-cols-7 flex-1 border-t border-l rounded-lg overflow-hidden" style={{ borderColor: 'var(--border-color)' }}>
        {weeks.flat().map((day) => {
          const dayEvents = getEventsForDate(day.date)
          const isSelected = day.date === selectedDate

          return (
            <button
              key={day.date}
              onClick={() => onSelectDate(day.date)}
              className={`
                min-h-[80px] p-1.5 border-r border-b text-left transition-colors
                ${!day.isCurrentMonth ? 'opacity-35' : ''}
                ${day.isToday ? 'ring-2 ring-inset' : ''}
                ${isSelected ? 'ring-2 ring-inset' : ''}
              `}
              style={{
                borderColor: 'var(--border-color)',
                backgroundColor: day.isToday
                  ? 'var(--today-bg)'
                  : isSelected
                    ? 'var(--bg-hover)'
                    : 'transparent',
                '--tw-ring-color': day.isToday ? 'var(--today-border)' : '#6366F1',
              } as React.CSSProperties}
            >
              {/* 日期数字 */}
              <span
                className={`text-sm font-medium ${day.isToday ? 'font-bold' : ''}`}
                style={{ color: day.isToday ? 'var(--today-border)' : 'var(--text-primary)' }}
              >
                {day.day}
              </span>

              {/* 活动色条 */}
              <div className="flex flex-col gap-0.5 mt-1">
                {dayEvents.slice(0, 3).map((event) => (
                  <div
                    key={event.id}
                    className="h-1.5 rounded-full"
                    style={{
                      backgroundColor: `var(--color-${event.game === 'genshin-impact' ? 'genshin' : event.game === 'honkai-star-rail' ? 'hsr' : 'zzz'})`,
                    }}
                  />
                ))}
                {dayEvents.length > 3 && (
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    +{dayEvents.length - 3}
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
