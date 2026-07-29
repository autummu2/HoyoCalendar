interface CompletionFilterProps {
  /** 选中的状态列表，空数组 = 全部 */
  selected: ('incomplete' | 'complete')[]
  onChange: (selected: ('incomplete' | 'complete')[]) => void
}

const OPTIONS: { key: 'incomplete' | 'complete'; label: string }[] = [
  { key: 'incomplete', label: '未完成' },
  { key: 'complete', label: '已完成' },
]

/**
 * 活动完成状态筛选器 — 与 GameFilter 相同的复选逻辑
 * 两个都不选 = 全部，两个都选 = 全部
 */
export function CompletionFilter({ selected, onChange }: CompletionFilterProps) {
  const toggle = (key: 'incomplete' | 'complete') => {
    if (selected.includes(key)) {
      onChange(selected.filter((k) => k !== key))
    } else {
      onChange([...selected, key])
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-medium mr-1" style={{ color: 'var(--text-secondary)' }}>
        状态
      </span>
      {OPTIONS.map(({ key, label }) => {
        const active = selected.includes(key)
        return (
          <button
            key={key}
            onClick={() => toggle(key)}
            className="text-xs px-2.5 py-1 rounded-full border transition-colors"
            style={{
              borderColor: active ? '#6366F1' : 'var(--border-color)',
              backgroundColor: active ? '#6366F1' : 'transparent',
              color: active ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
