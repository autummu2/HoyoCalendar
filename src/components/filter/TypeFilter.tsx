import type { EventTypeId } from '../../types/events'
import { EVENT_TYPE_META } from '../../types/events'

interface TypeFilterProps {
  selected: string[]
  onChange: (types: string[]) => void
}

const ALL_TYPES = Object.keys(EVENT_TYPE_META) as string[]

/**
 * 活动类型筛选器 — 横向按钮组
 */
export function TypeFilter({ selected, onChange }: TypeFilterProps) {
  const isAll = selected.length === 0

  const toggle = (type: string) => {
    if (selected.includes(type)) {
      onChange(selected.filter((t) => t !== type))
    } else {
      onChange([...selected, type])
    }
  }

  const selectAll = () => onChange([])

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs font-medium mr-1" style={{ color: 'var(--text-secondary)' }}>
        类型
      </span>

      <button
        onClick={selectAll}
        className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
          isAll
            ? 'bg-gray-800 text-white border-gray-800 dark:bg-white dark:text-gray-800 dark:border-white'
            : 'border-gray-300 text-gray-500 hover:border-gray-400'
        }`}
        style={!isAll ? { borderColor: 'var(--border-color)' } : {}}
      >
        全部
      </button>

      {ALL_TYPES.map((type) => {
        const meta = EVENT_TYPE_META[type as EventTypeId] ?? { icon: '📌', label: type }
        const active = selected.includes(type)
        return (
          <button
            key={type}
            onClick={() => toggle(type)}
            className="text-xs px-2 py-1 rounded-full border transition-colors"
            style={{
              borderColor: active ? '#6366F1' : 'var(--border-color)',
              backgroundColor: active ? '#6366F1' : 'transparent',
              color: active ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {meta.icon} {meta.label}
          </button>
        )
      })}
    </div>
  )
}
