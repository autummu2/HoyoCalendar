import type { Game } from '../../types/events'
import { GAME_META } from '../../types/events'

type FilterState = Record<string, 'include' | 'exclude'>

interface GameFilterProps {
  state: FilterState
  onChange: (state: FilterState) => void
}

const ALL_GAMES = Object.keys(GAME_META) as Game[]

/**
 * 游戏筛选器 — 三态按钮
 * 点击循环: 无 → 包含(蓝) → 排除(红) → 无
 */
export function GameFilter({ state, onChange }: GameFilterProps) {
  const toggle = (game: string) => {
    const next = { ...state }
    const current = next[game]
    if (!current) {
      next[game] = 'include'
    } else if (current === 'include') {
      next[game] = 'exclude'
    } else {
      delete next[game]
    }
    onChange(next)
  }

  const clearAll = () => onChange({})

  const hasAny = Object.keys(state).length > 0

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-medium mr-1" style={{ color: 'var(--text-secondary)' }}>
        游戏
      </span>

      <button
        onClick={clearAll}
        className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
          !hasAny
            ? 'bg-gray-800 text-white border-gray-800 dark:bg-white dark:text-gray-800 dark:border-white'
            : 'border-gray-300 text-gray-500 hover:border-gray-400'
        }`}
        style={hasAny ? { borderColor: 'var(--border-color)' } : {}}
      >
        全部
      </button>

      {ALL_GAMES.map((game) => {
        const meta = GAME_META[game]
        const value = state[game]
        const isInclude = value === 'include'
        const isExclude = value === 'exclude'
        const isActive = !!value

        return (
          <button
            key={game}
            onClick={() => toggle(game)}
            className="text-xs px-2.5 py-1 rounded-full border transition-colors"
            style={{
              borderColor: isActive ? (isInclude ? meta.color : '#EF4444') : 'var(--border-color)',
              backgroundColor: isActive ? (isInclude ? meta.color : '#FEE2E2') : 'transparent',
              color: isActive ? (isInclude ? '#fff' : '#DC2626') : 'var(--text-secondary)',
            }}
          >
            {meta.name}
            {isExclude ? ' ✕' : ''}
          </button>
        )
      })}
    </div>
  )
}
