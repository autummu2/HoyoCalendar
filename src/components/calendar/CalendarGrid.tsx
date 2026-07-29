import { useMemo } from 'react'
import type { CalendarDay } from '../../lib/date-utils'
import type { GameEvent } from '../../types/events'
import { WEEKDAY_LABELS } from '../../lib/constants'
import { computeEventSegments } from '../../lib/event-layout'

const BAR_HEIGHT = 22
const BAR_GAP = 3
const BAR_LANE_H = BAR_HEIGHT + BAR_GAP // 25px per lane
const MIN_CELL_H = 56 // 每格最小高度

interface CalendarGridProps {
  weeks: CalendarDay[][]
  events: GameEvent[]
  selectedDate: string | null
  onSelectDate: (date: string) => void
  onSelectEvent?: (date: string, eventId: string) => void
}

/**
 * 日历月视图网格组件 — Paimon.moe 风格
 *
 * 三层渲染架构（每周围）：
 *   Layer 1 (z-0): 格子背景（今日高亮、选中态），可点击选中日期
 *   Layer 2 (z-10): 活动色条，容器 pointer-events-none，色条自身可点击
 *   Layer 3 (z-20): 日期数字，pointer-events-none，浮在最上层
 */
export function CalendarGrid({ weeks, events, selectedDate, onSelectDate, onSelectEvent }: CalendarGridProps) {
  const weekSegments = useMemo(
    () => computeEventSegments(weeks, events),
    [weeks, events],
  )

  return (
    <div className="flex-1 flex flex-col px-6 pb-6">
      {/* ===== 星期头 ===== */}
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

      {/* ===== 日历主体（按周分行） ===== */}
      <div
        className="flex flex-col flex-1 border-t border-l rounded-lg overflow-hidden"
        style={{ borderColor: 'var(--border-color)' }}
      >
        {weeks.map((week, wi) => {
          const segs = weekSegments[wi]
          const maxLane = segs.length > 0 ? Math.max(...segs.map((s) => s.lane)) : 0
          const barsAreaH = segs.length > 0 ? (maxLane + 1) * BAR_LANE_H + 8 : 0

          return (
            <div
              key={wi}
              className="relative flex-1 border-b"
              style={{
                borderColor: 'var(--border-color)',
                minHeight: Math.max(barsAreaH + MIN_CELL_H, MIN_CELL_H),
              }}
            >
              {/* ======== Layer 1: 格子背景层 (z-0) — 从色条区下方开始 ======== */}
              <div
                className="grid grid-cols-7 absolute inset-x-0 bottom-0 z-0"
                style={{ top: barsAreaH }}
              >
                {week.map((day) => {
                  const isSelected = day.date === selectedDate
                  return (
                    <button
                      key={day.date}
                      onClick={() => onSelectDate(day.date)}
                      className={`
                        border-r border-b text-left transition-colors
                        ${!day.isCurrentMonth ? 'opacity-35' : ''}
                        ${day.isToday ? 'ring-2 ring-inset' : ''}
                        ${isSelected ? 'ring-2 ring-inset' : ''}
                        hover:bg-gray-50 dark:hover:bg-gray-800/50
                      `}
                      style={{
                        borderColor: 'var(--border-color)',
                        backgroundColor: day.isToday
                          ? 'var(--today-bg)'
                          : isSelected
                            ? 'var(--bg-hover)'
                            : 'transparent',
                        '--tw-ring-color': day.isToday
                          ? 'var(--today-border)'
                          : '#6366F1',
                      } as React.CSSProperties}
                    />
                  )
                })}
              </div>

              {/* ======== Layer 2: 活动色条层 (z-10) ======== */}
              {segs.length > 0 && (
                <div
                  className="absolute inset-x-0 z-10 pointer-events-none"
                  style={{ top: 4, height: barsAreaH }}
                >
                  {segs.map((seg) => {
                    const leftPct = (seg.startCol / 7) * 100
                    const widthPct = ((seg.endCol - seg.startCol + 1) / 7) * 100
                    const borderRadius = [
                      seg.isStart ? '6px' : '2px',
                      seg.isEnd ? '6px' : '2px',
                      seg.isEnd ? '6px' : '2px',
                      seg.isStart ? '6px' : '2px',
                    ].join(' ')

                    return (
                      <button
                        key={seg.eventId}
                        className="absolute flex items-center px-1.5 overflow-hidden select-none pointer-events-auto cursor-pointer hover:brightness-95 transition-[filter]"
                        style={{
                          left: `${leftPct}%`,
                          width: `calc(${widthPct}% - 4px)`,
                          top: seg.lane * BAR_LANE_H,
                          height: BAR_HEIGHT,
                          borderRadius,
                          ...(seg.bgImage
                            ? {
                                backgroundImage: `url(${seg.bgImage})`,
                                backgroundSize: 'cover',
                                backgroundPosition: 'center',
                              }
                            : {
                                backgroundColor: seg.color,
                                border: '1px solid rgba(0,0,0,0.08)',
                              }),
                        }}
                        title={seg.title}
                        onClick={() => onSelectEvent?.(week[seg.startCol].date, seg.eventId)}
                      >
                        {seg.bgImage && (
                          <div
                            className="absolute inset-0"
                            style={{ backgroundColor: 'rgba(0,0,0,0.45)', borderRadius }}
                          />
                        )}
                        <span
                          className="relative z-10 text-[11px] truncate font-medium leading-none"
                          style={{ color: seg.bgImage ? '#fff' : '#1E293B' }}
                        >
                          {seg.title}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}

              {/* ======== Layer 3: 日期数字层 (z-20) — 与格子背景同区域 ======== */}
              <div
                className="grid grid-cols-7 absolute inset-x-0 bottom-0 z-20 pointer-events-none"
                style={{ top: barsAreaH }}
              >
                {week.map((day) => (
                  <div
                    key={day.date}
                    className="p-1.5 border-r border-b"
                    style={{ borderColor: 'var(--border-color)' }}
                  >
                    <span
                      className={`text-sm font-medium ${day.isToday ? 'font-bold' : ''} ${!day.isCurrentMonth ? 'opacity-35' : ''}`}
                      style={{
                        color: day.isToday ? 'var(--today-border)' : 'var(--text-primary)',
                      }}
                    >
                      {day.day}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
