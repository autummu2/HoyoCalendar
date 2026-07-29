import type { Game } from '../../types/events'
import { GAME_META } from '../../types/events'

interface GameFilterProps {
  selected: Game[]
  onChange: (games: Game[]) => void
}

const ALL_GAMES = Object.keys(GAME_META) as Game[]

/**
 * 游戏筛选器 — 横向按钮组
 * 点击切换选中状态，全部未选中 = 显示全部
 */
export function GameFilter({ selected, onChange }: GameFilterProps) {
  const isAll = selected.length === 0

  const toggle = (game: Game) => {
    if (selected.includes(game)) {
      const next = selected.filter((g) => g !== game)
      onChange(next)
    } else {
      onChange([...selected, game])
    }
  }

  const selectAll = () => onChange([])

  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs font-medium mr-1" style={{ color: 'var(--text-secondary)' }}>
        游戏
      </span>

      {/* "全部" 按钮 */}
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

      {ALL_GAMES.map((game) => {
        const meta = GAME_META[game]
        const active = selected.includes(game)
        return (
          <button
            key={game}
            onClick={() => toggle(game)}
            className="text-xs px-2.5 py-1 rounded-full border transition-colors"
            style={{
              borderColor: active ? meta.color : 'var(--border-color)',
              backgroundColor: active ? meta.color : 'transparent',
              color: active ? '#fff' : 'var(--text-secondary)',
            }}
          >
            {meta.name}
          </button>
        )
      })}
    </div>
  )
}
