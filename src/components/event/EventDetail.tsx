import type { GameEvent } from '../../types/events'
import { GAME_META, EVENT_TYPE_META } from '../../types/events'

interface EventDetailProps {
  events: GameEvent[]
  date: string
  highlightedEventId?: string | null
  isCompleted?: (eventId: string) => boolean
  onToggleComplete?: (eventId: string) => void
  onClose: () => void
}

export function EventDetail({ events, date, highlightedEventId, isCompleted, onToggleComplete, onClose }: EventDetailProps) {
  if (events.length === 0) {
    return (
      <aside
        className="w-80 border-l p-4 overflow-y-auto"
        style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-surface)' }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
            {date}
          </h3>
          <button onClick={onClose} className="text-sm" style={{ color: 'var(--text-muted)' }}>
            ✕
          </button>
        </div>
        <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
          当日无活动
        </p>
      </aside>
    )
  }

  return (
    <aside
      className="w-80 border-l p-4 overflow-y-auto"
      style={{ borderColor: 'var(--border-color)', backgroundColor: 'var(--bg-surface)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold" style={{ color: 'var(--text-primary)' }}>
          {date}
        </h3>
        <button onClick={onClose} className="text-sm hover:opacity-70" style={{ color: 'var(--text-muted)' }}>
          ✕
        </button>
      </div>

      <ul className="space-y-3">
        {events.map((event) => {
          const gameMeta = GAME_META[event.game]
          const typeMeta = EVENT_TYPE_META[event.type]

          return (
            <li
              key={event.id}
              className={`rounded-lg p-3 border transition-all ${event.id === highlightedEventId ? 'ring-2 ring-blue-400 shadow-sm' : ''}`}
              style={{
                borderColor: event.id === highlightedEventId ? '#60A5FA' : 'var(--border-color)',
                opacity: isCompleted?.(event.id) ? 0.55 : 1,
              }}
            >
              {/* 游戏标签 + 类型标签 + 完成切换 */}
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

              {/* 活动标题 */}
              <h4 className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>
                {event.title}
              </h4>

              {/* 时间范围 */}
              <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
                {event.start_date} ~ {event.end_date}
              </p>

              {/* 描述 */}
              {event.description && (
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {event.description}
                </p>
              )}

              {/* 标签 */}
              {event.tags && event.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
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
    </aside>
  )
}
