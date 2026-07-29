import { describe, it, expect } from 'vitest'
import {
  getDaysInMonth,
  formatDate,
  parseDate,
  isDateInRange,
  getToday,
  buildCalendarGrid,
} from './date-utils'

describe('getDaysInMonth', () => {
  it('returns 31 for January', () => {
    expect(getDaysInMonth(2026, 1)).toBe(31)
  })
  it('returns 28 for February in non-leap year', () => {
    expect(getDaysInMonth(2025, 2)).toBe(28)
  })
  it('returns 29 for February in leap year', () => {
    expect(getDaysInMonth(2024, 2)).toBe(29)
  })
  it('returns 30 for April', () => {
    expect(getDaysInMonth(2026, 4)).toBe(30)
  })
})

describe('formatDate', () => {
  it('formats a date as YYYY-MM-DD', () => {
    expect(formatDate(new Date(2026, 7, 5))).toBe('2026-08-05')
  })
  it('pads single-digit month and day', () => {
    expect(formatDate(new Date(2026, 0, 1))).toBe('2026-01-01')
  })
})

describe('parseDate', () => {
  it('parses YYYY-MM-DD to Date', () => {
    const d = parseDate('2026-08-15')
    expect(d.getFullYear()).toBe(2026)
    expect(d.getMonth()).toBe(7) // 0-based
    expect(d.getDate()).toBe(15)
  })
})

describe('isDateInRange', () => {
  it('returns true when date is within range', () => {
    expect(isDateInRange('2026-08-10', '2026-08-01', '2026-08-31')).toBe(true)
  })
  it('returns true on start boundary', () => {
    expect(isDateInRange('2026-08-01', '2026-08-01', '2026-08-31')).toBe(true)
  })
  it('returns true on end boundary', () => {
    expect(isDateInRange('2026-08-31', '2026-08-01', '2026-08-31')).toBe(true)
  })
  it('returns false before range', () => {
    expect(isDateInRange('2026-07-31', '2026-08-01', '2026-08-31')).toBe(false)
  })
  it('returns false after range', () => {
    expect(isDateInRange('2026-09-01', '2026-08-01', '2026-08-31')).toBe(false)
  })
})

describe('buildCalendarGrid', () => {
  it('returns 6 rows', () => {
    const grid = buildCalendarGrid(2026, 8)
    expect(grid).toHaveLength(6)
  })

  it('each row has 7 days', () => {
    const grid = buildCalendarGrid(2026, 8)
    for (const row of grid) {
      expect(row).toHaveLength(7)
    }
  })

  it('first cell of first row is a Monday', () => {
    // Aug 2026 starts on a Saturday. So first cell should be Mon Jul 27
    const grid = buildCalendarGrid(2026, 8)
    expect(grid[0][0].date).toBe('2026-07-27') // Monday
  })

  it('contains today marked', () => {
    const today = getToday()
    const grid = buildCalendarGrid(2026, 8)
    const flat = grid.flat()
    const todayCell = flat.find((c) => c.date === today)
    expect(todayCell?.isToday).toBe(true)
  })

  it('current month cells are marked correctly', () => {
    const grid = buildCalendarGrid(2026, 8)
    const flat = grid.flat()
    const augCells = flat.filter((c) => c.isCurrentMonth)
    expect(augCells).toHaveLength(31) // August has 31 days
  })
})
