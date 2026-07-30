import type { GameEvent, EventTypeId } from '../../types/events'
import { GAME_META, EVENT_TYPE_META } from '../../types/events'
import { formatDayLabel } from '../layout/Header'

interface DayViewProps {
  date: string
  events: GameEvent[]
  highlightedEventId?: string | null
  isCompleted?: (eventId: string) => boolean
  onToggleComplete?: (eventId: string) => void
  onSelectEvent?: (eventId: string) => void
}

/**
 * 日视图 — 将当天活动以卡片列表形式展示
 */
export function DayView({ date, events, highlightedEventId, isCompleted, onToggleComplete, onSelectEvent }: DayViewProps) {
  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      {/* 日期标题 */}
      <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        {formatDayLabel(date)}
      </h2>

      {events.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          当日无活动
        </p>
      ) : (
        <ul className="space-y-3 max-w-2xl">
          {events.map((event) => {
            const gameMeta = GAME_META[event.game]
            const typeMeta = EVENT_TYPE_META[event.type as EventTypeId] ?? { icon: '📌', label: event.type }
            const isHighlighted = event.id === highlightedEventId

            return (
              <li
                key={event.id}
                className={`rounded-lg p-4 border cursor-pointer transition-all hover:shadow-sm ${
                  isHighlighted ? 'ring-2 ring-blue-400 shadow-sm' : ''
                }`}
                style={{
                  borderColor: isHighlighted ? '#60A5FA' : 'var(--border-color)',
                  backgroundColor: 'var(--bg-surface)',
                  borderLeftWidth: '4px',
                  borderLeftColor: event.color ?? gameMeta.color,
                  opacity: isCompleted?.(event.id) ? 0.55 : 1,
                }}
                onClick={() => onSelectEvent?.(event.id)}
              >
                {/* 游戏标签 + 类型 + 完成切换 */}
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className="text-xs px-2 py-0.5 rounded-full text-white font-medium"
                    style={{ backgroundColor: gameMeta.color }}
                  >
                    {gameMeta.name}
                  </span>
                  <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    {typeMeta.icon} {typeMeta.label}
                  </span>
                  <div className="flex-1" />
                  {onToggleComplete && (
                    <button
                      onClick={(e) => { e.stopPropagation(); onToggleComplete(event.id) }}
                      className={`text-sm w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                        isCompleted?.(event.id)
                          ? 'bg-green-500 border-green-500 text-white'
                          : 'border-gray-300 text-transparent hover:border-gray-400'
                      }`}
                      title={isCompleted?.(event.id) ? '标记为未完成' : '标记为完成'}
                    >
                      ✓
                    </button>
                  )}
                </div>

                {/* 标题 */}
                <h3 className="font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                  {event.title}
                </h3>

                {/* 时间范围 */}
                <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
                  {event.start_date} ~ {event.end_date}
                </p>

                {/* 描述 */}
                {event.description && (
                  <p className="text-sm mb-2" style={{ color: 'var(--text-secondary)' }}>
                    {event.description}
                  </p>
                )}

                {/* 链接 */}
                {event.source_url && (
                  <a
                    href={event.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-500 hover:underline inline-block mb-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    🔗 {new URL(event.source_url).hostname}
                  </a>
                )}

                {/* 标签 */}
                {event.tags && event.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {event.tags.map((tag) => (
                      <span
                        key={tag}
                        className="text-xs px-2 py-0.5 rounded-full"
                        style={{ backgroundColor: 'var(--bg-hover)', color: 'var(--text-secondary)' }}
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
