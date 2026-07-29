/**
 * 日期工具函数
 * 所有日期操作均为纯函数，不修改输入参数
 */

/**
 * 获取某个月的天数
 */
export function getDaysInMonth(year: number, month: number): number {
  // month: 1-based (1 = January)
  return new Date(year, month, 0).getDate()
}

/**
 * 获取某个月第一天是星期几
 * 返回: 0 = 周日, 1 = 周一, ..., 6 = 周六
 */
export function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month - 1, 1).getDay()
}

/**
 * 将 Date 转为 YYYY-MM-DD 字符串
 */
export function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 解析 YYYY-MM-DD 为 Date
 */
export function parseDate(str: string): Date {
  const [y, m, d] = str.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/**
 * 判断日期是否在区间内（含首尾）
 */
export function isDateInRange(date: string, start: string, end: string): boolean {
  return date >= start && date <= end
}

/**
 * 获取今天的 YYYY-MM-DD 字符串
 */
export function getToday(): string {
  return formatDate(new Date())
}

/**
 * 生成日历网格所需的日期数组
 * 返回 6 行 × 7 列的二维数组，包含上月/当月/下月的日期
 */
export interface CalendarDay {
  date: string         // YYYY-MM-DD
  day: number          // 几号 (1-31)
  isCurrentMonth: boolean
  isToday: boolean
}

export function buildCalendarGrid(year: number, month: number): CalendarDay[][] {
  const today = getToday()
  const daysInMonth = getDaysInMonth(year, month)
  const firstDay = getFirstDayOfMonth(year, month)

  // 将周日(0)转换为一周从周一开始的体系
  // 周一=0, 周二=1, ..., 周日=6
  const startOffset = firstDay === 0 ? 6 : firstDay - 1

  const grid: CalendarDay[][] = []
  let currentWeek: CalendarDay[] = []

  // 上月填充
  const prevMonth = month === 1 ? 12 : month - 1
  const prevYear = month === 1 ? year - 1 : year
  const daysInPrevMonth = getDaysInMonth(prevYear, prevMonth)

  for (let i = startOffset - 1; i >= 0; i--) {
    const day = daysInPrevMonth - i
    const date = `${prevYear}-${String(prevMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    currentWeek.push({ date, day, isCurrentMonth: false, isToday: date === today })
  }

  // 当月
  for (let day = 1; day <= daysInMonth; day++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    currentWeek.push({ date, day, isCurrentMonth: true, isToday: date === today })
    if (currentWeek.length === 7) {
      grid.push(currentWeek)
      currentWeek = []
    }
  }

  // 下月填充
  if (currentWeek.length > 0) {
    const nextMonth = month === 12 ? 1 : month + 1
    const nextYear = month === 12 ? year + 1 : year
    let day = 1
    while (currentWeek.length < 7) {
      const date = `${nextYear}-${String(nextMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`
      currentWeek.push({ date, day, isCurrentMonth: false, isToday: date === today })
      day++
    }
    grid.push(currentWeek)
  }

  return grid
}
