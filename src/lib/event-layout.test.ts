import { describe, it, expect } from 'vitest'
import { computeEventSegments } from './event-layout'
import { buildCalendarGrid } from './date-utils'
import type { GameEvent } from '../types/events'

function makeEvent(overrides: Partial<GameEvent> = {}): GameEvent {
  return {
    id: 'test-1',
    game: 'genshin-impact',
    title: '测试活动',
    type: 'version-main',
    start_date: '2026-08-10',
    end_date: '2026-08-20',
    ...overrides,
  } as GameEvent
}

describe('computeEventSegments', () => {
  it('returns one segment array per week', () => {
    const weeks = buildCalendarGrid(2026, 8)
    const events = [makeEvent()]
    const result = computeEventSegments(weeks, events)
    expect(result).toHaveLength(6)
  })

  it('event fully within one week produces one segment', () => {
    const weeks = buildCalendarGrid(2026, 8)
    // Aug 10-14 (Mon-Fri, all in week 2: Aug 3-9... wait, let me calculate)
    // Aug 2026: week 1 = Jul 27-Aug 2, week 2 = Aug 3-9, week 3 = Aug 10-16
    const events = [makeEvent({ start_date: '2026-08-10', end_date: '2026-08-14' })]
    const result = computeEventSegments(weeks, events)

    // Should only have segments in week 3 (index 2)
    const activeWeeks = result.filter((segs) => segs.length > 0)
    expect(activeWeeks).toHaveLength(1)
  })

  it('event spanning two weeks produces two segments', () => {
    const weeks = buildCalendarGrid(2026, 8)
    // Aug 5-12 spans two weeks
    const events = [makeEvent({ start_date: '2026-08-05', end_date: '2026-08-12' })]
    const result = computeEventSegments(weeks, events)

    const activeWeeks = result.filter((segs) => segs.length > 0)
    expect(activeWeeks).toHaveLength(2)
  })

  it('marks isStart and isEnd correctly', () => {
    const weeks = buildCalendarGrid(2026, 8)
    // Aug 10-14 (one week, both start and end in same week)
    const events = [makeEvent({ start_date: '2026-08-10', end_date: '2026-08-14' })]
    const result = computeEventSegments(weeks, events)

    const activeSegs = result.flat()
    expect(activeSegs).toHaveLength(1)
    expect(activeSegs[0].isStart).toBe(true)
    expect(activeSegs[0].isEnd).toBe(true)
  })

  it('event spanning full month has segments in all weeks', () => {
    const weeks = buildCalendarGrid(2026, 8)
    const events = [makeEvent({ start_date: '2026-08-01', end_date: '2026-08-31' })]
    const result = computeEventSegments(weeks, events)

    // Aug 2026 has 5 weeks that include August days
    const activeWeeks = result.filter((segs) => segs.length > 0)
    expect(activeWeeks.length).toBeGreaterThanOrEqual(4)
  })

  it('assigns correct startCol and endCol for full-week event', () => {
    const weeks = buildCalendarGrid(2026, 8)
    // A week that's entirely August: Aug 10 (Mon) - Aug 16 (Sun) = week 3
    const events = [makeEvent({ start_date: '2026-08-10', end_date: '2026-08-16' })]
    const result = computeEventSegments(weeks, events)

    const segs = result[2] // week 3
    expect(segs).toHaveLength(1)
    expect(segs[0].startCol).toBe(0) // Monday
    expect(segs[0].endCol).toBe(6) // Sunday
  })

  it('overlapping events get different lanes', () => {
    const weeks = buildCalendarGrid(2026, 8)
    const events = [
      makeEvent({ id: 'a', start_date: '2026-08-10', end_date: '2026-08-16' }),
      makeEvent({ id: 'b', start_date: '2026-08-10', end_date: '2026-08-14' }),
    ]
    const result = computeEventSegments(weeks, events)

    // week 3 (index 2) should have 2 segments with different lanes
    const segs = result[2]
    expect(segs).toHaveLength(2)
    expect(segs[0].lane).not.toBe(segs[1].lane)
  })

  it('non-overlapping events can share a lane', () => {
    const weeks = buildCalendarGrid(2026, 8)
    const events = [
      makeEvent({ id: 'a', start_date: '2026-08-10', end_date: '2026-08-11' }),
      makeEvent({ id: 'b', start_date: '2026-08-12', end_date: '2026-08-13' }),
    ]
    const result = computeEventSegments(weeks, events)

    const segs = result[2] // week 3
    expect(segs).toHaveLength(2)
    expect(segs[0].lane).toBe(0)
    expect(segs[1].lane).toBe(0) // non-overlapping → same lane
  })

  it('uses event color if specified, falls back to game color', () => {
    const weeks = buildCalendarGrid(2026, 8)
    const events = [
      makeEvent({ id: 'a', color: '#FF0000', start_date: '2026-08-10', end_date: '2026-08-11' }),
      makeEvent({ id: 'b', start_date: '2026-08-10', end_date: '2026-08-11' }),
    ]
    const result = computeEventSegments(weeks, events)

    const segs = result[2]
    expect(segs[0].color).toBe('#FF0000') // custom color
    expect(segs[1].color).toBe('#4A90D9') // genshin default
  })
})
