import { useMemo } from 'react'
import type { CalendarDay } from '../../lib/date-utils'
import type { GameEvent } from '../../types/events'
import { WEEKDAY_LABELS } from '../../lib/constants'
import { computeEventSegments } from '../../lib/event-layout'

const BAR_HEIGHT = 22
const BAR_GAP = 3
const BAR_LANE_H = BAR_HEIGHT + BAR_GAP // 25px per lane

interface CalendarGridProps {
  weeks: CalendarDay[][]
  events: GameEvent[]
  selectedDate: string | null
  onSelectDate: (date: string) => void
}

/**
 * 日历月视图网格组件 — Paimon.moe 风格
 *
 * 每个活动渲染为跨越多天的连续色条，显示活动标题。
 * 多活动垂直堆叠，贪心算法分配通道避免遮挡。
 */
export function CalendarGrid({ weeks, events, selectedDate, onSelectDate }: CalendarGridProps) {
  // 为整个月计算色条分段（按周分组）
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
          const barsAreaHeight = segs.length > 0 ? (maxLane + 1) * BAR_LANE_H : 0

          return (
            <div
              key={wi}
              className="relative flex-1 border-b"
              style={{ borderColor: 'var(--border-color)' }}
            >
              {/* ---- 活动色条层 ---- */}
              {segs.length > 0 && (
                <div
                  className="absolute inset-x-0 z-10 pointer-events-none"
                  style={{ top: 4, height: barsAreaHeight }}
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
                      <div
                        key={seg.eventId}
                        className="absolute flex items-center px-1.5 overflow-hidden select-none"
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
                              }),
                        }}
                        title={seg.title}
                      >
                        {/* 图片背景时加遮罩保证文字可读 */}
                        {seg.bgImage && (
                          <div
                            className="absolute inset-0"
                            style={{ backgroundColor: 'rgba(0,0,0,0.45)', borderRadius }}
                          />
                        )}
                        <span className="relative z-10 text-[11px] text-white truncate font-medium leading-none drop-shadow-sm">
                          {seg.title}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* ---- 日期格子层 ---- */}
              <div
                className="grid grid-cols-7 h-full"
                style={{ paddingTop: barsAreaHeight > 0 ? barsAreaHeight + 6 : 0 }}
              >
                {week.map((day) => {
                  const isSelected = day.date === selectedDate

                  return (
                    <button
                      key={day.date}
                      onClick={() => onSelectDate(day.date)}
                      className={`
                        min-h-[56px] p-1.5 border-r text-left transition-colors relative z-20
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
                        '--tw-ring-color': day.isToday ? 'var(--today-border)' : '#6366F1',
                      } as React.CSSProperties}
                    >
                      <span
                        className={`text-sm font-medium relative z-20 ${day.isToday ? 'font-bold' : ''}`}
                        style={{
                          color: day.isToday ? 'var(--today-border)' : 'var(--text-primary)',
                        }}
                      >
                        {day.day}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
