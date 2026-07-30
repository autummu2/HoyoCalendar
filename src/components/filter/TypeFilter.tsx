interface TypeFilterProps {
  /** 所有可用类型（从事件数据中动态收集） */
  availableTypes: string[]
  selected: string[]
  onChange: (types: string[]) => void
}

/**
 * 活动类型筛选器 — 动态收集可选类型
 */
export function TypeFilter({ availableTypes, selected, onChange }: TypeFilterProps) {
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

      {availableTypes.map((type) => {
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
            {type}
          </button>
        )
      })}
    </div>
  )
}
