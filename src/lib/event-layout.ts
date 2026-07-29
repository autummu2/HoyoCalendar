import type { GameEvent } from '../types/events'
import { GAME_META } from '../types/events'
import type { CalendarDay } from './date-utils'
import { isDateInRange } from './date-utils'

/**
 * 活动色条在日历一周行内的分段信息
 */
export interface EventBarSegment {
  eventId: string
  title: string
  game: string
  startCol: number   // 0-6，该周内的起始列（周一=0）
  endCol: number     // 0-6，该周内的结束列（含）
  lane: number       // 垂直堆叠通道（0起）
  isStart: boolean   // 活动是否从本周开始
  isEnd: boolean     // 活动是否在本周结束
  color: string      // 背景色
  bgImage?: string   // 背景图片 URL（优先级高于 color）
}

/**
 * 计算所有活动在日历各周中的色条分段
 *
 * 返回 weeks.length 个数组，每个对应一周的色条列表。
 * 色条已分配好 lane，保证同一周内重叠的活动不会相互遮挡。
 */
export function computeEventSegments(
  weeks: CalendarDay[][],
  events: GameEvent[],
): EventBarSegment[][] {
  return weeks.map((week) => {
    const weekStart = week[0].date
    const weekEnd = week[6].date

    // 1. 收集本周有活动的所有分段
    const segments: EventBarSegment[] = []

    for (const event of events) {
      // 活动与本周无交集则跳过
      if (event.end_date < weekStart || event.start_date > weekEnd) continue

      let startCol = -1
      let endCol = -1

      for (let col = 0; col < 7; col++) {
        if (isDateInRange(week[col].date, event.start_date, event.end_date)) {
          if (startCol === -1) startCol = col
          endCol = col
        }
      }

      if (startCol === -1) continue

      const gameMeta = GAME_META[event.game]

      segments.push({
        eventId: event.id,
        title: event.title,
        game: event.game,
        startCol,
        endCol,
        lane: 0,
        isStart: event.start_date >= weekStart && event.start_date <= weekEnd,
        isEnd: event.end_date >= weekStart && event.end_date <= weekEnd,
        color: event.color ?? gameMeta?.color ?? '#6B7280',
        bgImage: event.bar_bg_image,
      })
    }

    // 2. 贪心算法分配 lane（垂直通道），避免同列重叠
    // lanes[i] = 第 i 条 lane 当前被占用到哪一列
    const lanes: number[] = []

    segments.sort((a, b) => {
      // 先按起始列排，再按跨度长的排前面
      if (a.startCol !== b.startCol) return a.startCol - b.startCol
      return b.endCol - b.startCol - (a.endCol - a.startCol)
    })

    for (const seg of segments) {
      let lane = 0
      while (lane < lanes.length && lanes[lane] >= seg.startCol) {
        lane++
      }
      seg.lane = lane
      lanes[lane] = seg.endCol
    }

    return segments
  })
}
