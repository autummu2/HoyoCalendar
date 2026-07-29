import type { GameEvent } from '../types/events'
import { EventDataFileSchema } from '../types/events'

/**
 * 从静态 YAML/JSON 数据加载活动事件
 *
 * MVP 阶段直接 import 数据文件，通过 Vite 的静态 import 处理。
 * 远期 v1.0 迁移为 fetch API 调用。
 */

// 延迟导入 — 后续 Sprint 中将改用动态 import 或 glob import
let cachedEvents: GameEvent[] | null = null

export async function loadAllEvents(): Promise<GameEvent[]> {
  if (cachedEvents) return cachedEvents

  // TODO: Sprint 1 中替换为实际的 YAML import (Vite 支持)
  // 当前返回硬编码样本数据用于开发验证
  const sample: GameEvent[] = [
    {
      id: 'sample-1',
      game: 'genshin-impact',
      title: '「仿若无因飘落的轻雨」4.0 版本',
      type: 'version-main',
      description: '枫丹地区开放，全新水下探索玩法上线。',
      start_date: '2026-08-16',
      end_date: '2026-09-27',
      tags: ['版本更新', '枫丹'],
    },
    {
      id: 'sample-2',
      game: 'honkai-star-rail',
      title: '「碧羽飞黄」2.5 版本',
      type: 'version-main',
      description: '全新星球翁法罗斯篇章继续。',
      start_date: '2026-08-02',
      end_date: '2026-09-13',
      tags: ['版本更新', '飞霄'],
    },
    {
      id: 'sample-3',
      game: 'zenless-zone-zero',
      title: '「电子乱潮」1.3 版本',
      type: 'version-main',
      description: '全新剧情章节开放，新角色月城柳登场。',
      start_date: '2026-08-09',
      end_date: '2026-09-20',
      tags: ['版本更新', '月城柳'],
    },
  ]

  const parsed = EventDataFileSchema.safeParse(sample)
  if (!parsed.success) {
    console.error('Data validation error:', parsed.error.format())
    throw new Error('Invalid event data')
  }

  cachedEvents = parsed.data
  return cachedEvents
}

/**
 * 清除缓存（用于数据重载场景）
 */
export function clearEventCache(): void {
  cachedEvents = null
}
