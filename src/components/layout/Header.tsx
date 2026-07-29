import { WEEKDAY_LABELS } from '../../lib/constants'

type ViewMode = 'month' | 'week' | 'day'

interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  viewMode: ViewMode
  onChangeView: (mode: ViewMode) => void
  navLabel: string
  onPrev: () => void
  onNext: () => void
  onToday: () => void
}

const VIEW_OPTIONS: { mode: ViewMode; label: string }[] = [
  { mode: 'month', label: '月' },
  { mode: 'week', label: '周' },
  { mode: 'day', label: '日' },
]

export function Header({
  theme,
  onToggleTheme,
  viewMode,
  onChangeView,
  navLabel,
  onPrev,
  onNext,
  onToday,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'var(--border-color)' }}>
      {/* Left: Logo & Title + View Switcher */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🎮</span>
          <h1 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
            米游活动日历
          </h1>
        </div>

        {/* View Switcher */}
        <div className="flex items-center rounded-lg border" style={{ borderColor: 'var(--border-color)' }}>
          {VIEW_OPTIONS.map(({ mode, label }) => (
            <button
              key={mode}
              onClick={() => onChangeView(mode)}
              className="px-3 py-1 text-sm font-medium transition-colors first:rounded-l-lg last:rounded-r-lg"
              style={{
                backgroundColor: viewMode === mode ? 'var(--bg-hover)' : 'transparent',
                color: viewMode === mode ? 'var(--text-primary)' : 'var(--text-muted)',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Center: Navigation */}
      <div className="flex items-center gap-4">
        <button
          onClick={onPrev}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="上一级"
        >
          ◀
        </button>
        <h2 className="text-lg font-medium min-w-40 text-center" style={{ color: 'var(--text-primary)' }}>
          {navLabel}
        </h2>
        <button
          onClick={onNext}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="下一级"
        >
          ▶
        </button>
        <button
          onClick={onToday}
          className="px-3 py-1 text-sm rounded-md border transition-colors"
          style={{ borderColor: 'var(--border-color)', color: 'var(--text-secondary)' }}
        >
          今天
        </button>
      </div>

      {/* Right: Theme Toggle */}
      <button
        onClick={onToggleTheme}
        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-lg"
        aria-label="切换主题"
      >
        {theme === 'light' ? '🌙' : '☀️'}
      </button>
    </header>
  )
}

/** 格式化周视图导航标签 "8月4日 - 8月10日" */
export function formatWeekLabel(weekStart: string, weekEnd: string): string {
  const [, sm, sd] = weekStart.split('-').map(Number)
  const [, em, ed] = weekEnd.split('-').map(Number)
  if (sm === em) {
    return `${sm}月${sd}日 - ${ed}日`
  }
  return `${sm}月${sd}日 - ${em}月${ed}日`
}

/** 格式化日视图导航标签 "2026年8月5日 周二" */
export function formatDayLabel(date: string): string {
  const d = new Date(date)
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  const day = d.getDate()
  // getDay: 0=Sun → 6, 1=Mon → 0
  const wd = d.getDay() === 0 ? 6 : d.getDay() - 1
  return `${y}年${m}月${day}日 周${WEEKDAY_LABELS[wd]}`
}
