import { MONTH_LABELS } from '../../lib/constants'

interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  year: number
  month: number // 1-based
  onPrevMonth: () => void
  onNextMonth: () => void
  onToday: () => void
}

export function Header({
  theme,
  onToggleTheme,
  year,
  month,
  onPrevMonth,
  onNextMonth,
  onToday,
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between px-6 py-4 border-b" style={{ borderColor: 'var(--border-color)' }}>
      {/* Left: Logo & Title */}
      <div className="flex items-center gap-3">
        <span className="text-2xl">🎮</span>
        <h1 className="text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
          米游活动日历
        </h1>
      </div>

      {/* Center: Month Navigation */}
      <div className="flex items-center gap-4">
        <button
          onClick={onPrevMonth}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="上一月"
        >
          ◀
        </button>
        <h2 className="text-lg font-medium min-w-32 text-center" style={{ color: 'var(--text-primary)' }}>
          {year}年 {MONTH_LABELS[month - 1]}
        </h2>
        <button
          onClick={onNextMonth}
          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          aria-label="下一月"
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
