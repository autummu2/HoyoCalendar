type FilterState = Record<string, 'include' | 'exclude'>

interface TypeFilterProps {
  availableTypes: string[]
  state: FilterState
  onChange: (state: FilterState) => void
}

/**
 * 活动类型筛选器 — 三态按钮
 * 点击循环: 无 → 包含(蓝) → 排除(红) → 无
 */
export function TypeFilter({ availableTypes, state, onChange }: TypeFilterProps) {
  const toggle = (type: string) => {
    const next = { ...state }
    const current = next[type]
    if (!current) {
      next[type] = 'include'
    } else if (current === 'include') {
      next[type] = 'exclude'
    } else {
      delete next[type]
    }
    onChange(next)
  }

  const clearAll = () => onChange({})
  const hasAny = Object.keys(state).length > 0

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs font-medium mr-1" style={{ color: 'var(--text-secondary)' }}>
        类型
      </span>

      <button
        onClick={clearAll}
        className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
          !hasAny
            ? 'bg-gray-800 text-white border-gray-800 dark:bg-white dark:text-gray-800 dark:border-white'
            : 'border-gray-300 text-gray-500 hover:border-gray-400'
        }`}
        style={!hasAny ? {} : { borderColor: 'var(--border-color)' }}
      >
        全部
      </button>

      {availableTypes.map((type) => {
        const value = state[type]
        const isInclude = value === 'include'
        const isExclude = value === 'exclude'

        return (
          <button
            key={type}
            onClick={() => toggle(type)}
            className="text-xs px-2 py-1 rounded-full border transition-colors"
            style={{
              borderColor: isInclude ? '#6366F1' : isExclude ? '#EF4444' : 'var(--border-color)',
              backgroundColor: isInclude ? '#6366F1' : isExclude ? '#FEE2E2' : 'transparent',
              color: isInclude ? '#fff' : isExclude ? '#DC2626' : 'var(--text-secondary)',
            }}
          >
            {type}
            {isExclude ? ' ✕' : ''}
          </button>
        )
      })}
    </div>
  )
}
