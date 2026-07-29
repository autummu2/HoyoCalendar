import type { GameEvent } from '../types/events'
import { EventDataFileSchema } from '../types/events'

/**
 * 从静态 YAML/JSON 数据加载活动事件
 *
 * MVP 阶段直接 import 数据文件，通过 Vite 的静态 import 处理。
 * 远期 v1.0 迁移为 fetch API 调用。
 */

let cachedEvents: GameEvent[] | null = null

export async function loadAllEvents(): Promise<GameEvent[]> {
  if (cachedEvents) return cachedEvents

  // TODO: Sprint 1 中替换为实际的 YAML import (Vite 支持)
  // 当前返回硬编码样本数据用于开发验证
  const sample: GameEvent[] = [
    // === 原神 ===
    {
      id: 'sample-gi-version',
      game: 'genshin-impact',
      title: '「仿若无因飘落的轻雨」4.0 版本',
      type: 'version-main',
      description: '枫丹地区开放，全新水下探索玩法上线。',
      color: '#1E3A5F',
      start_date: '2026-08-16',
      end_date: '2026-09-27',
      tags: ['版本更新', '枫丹'],
    },
    {
      id: 'sample-gi-banner1',
      game: 'genshin-impact',
      title: '「光与影的戏术」林尼 + 夜兰 UP',
      type: 'banner',
      description: '限定五星角色「林尼（火弓）」+「夜兰（水弓）」概率UP',
      color: '#D97706',
      start_date: '2026-08-16',
      end_date: '2026-09-06',
      tags: ['卡池', '林尼', '夜兰'],
    },
    {
      id: 'sample-gi-event',
      game: 'genshin-impact',
      title: '「机枢巧物前哨战」主题活动',
      type: 'version-main',
      description: '枫丹机关探险活动，可获得专属四星武器。',
      color: '#0D9488',
      start_date: '2026-08-20',
      end_date: '2026-09-10',
      tags: ['版本活动', '机关'],
    },
    {
      id: 'sample-gi-abyss',
      game: 'genshin-impact',
      title: '深境螺旋 4.0 第一期',
      type: 'challenge',
      description: '本期深境螺旋 buff：蒸发/融化反应攻击力提升。',
      color: '#BE123C',
      start_date: '2026-08-16',
      end_date: '2026-09-01',
      tags: ['深境螺旋', '高难'],
    },

    // === 星穹铁道 ===
    {
      id: 'sample-hsr-version',
      game: 'honkai-star-rail',
      title: '「碧羽飞黄」2.5 版本',
      type: 'version-main',
      description: '全新星球翁法罗斯篇章继续，新角色飞霄登场。',
      color: '#4C1D95',
      start_date: '2026-08-02',
      end_date: '2026-09-13',
      tags: ['版本更新', '飞霄'],
    },
    {
      id: 'sample-hsr-banner1',
      game: 'honkai-star-rail',
      title: '「飙驭霆锋」飞霄 + 银狼 UP',
      type: 'banner',
      description: '限定五星角色「飞霄（雷巡猎）」+「银狼（量子虚无）」概率UP',
      color: '#C2410C',
      start_date: '2026-08-02',
      end_date: '2026-08-23',
      tags: ['卡池', '飞霄', '银狼'],
    },
    {
      id: 'sample-hsr-event',
      game: 'honkai-star-rail',
      title: '「星天演武」搏击俱乐部',
      type: 'challenge',
      description: '参与搏击挑战赛获取星琼、漫游指南等奖励。',
      color: '#059669',
      start_date: '2026-08-09',
      end_date: '2026-08-30',
      tags: ['活动', '挑战', '星琼'],
    },
    {
      id: 'sample-hsr-moc',
      game: 'honkai-star-rail',
      title: '忘却之庭·混沌回忆 2.5',
      type: 'challenge',
      description: '本期混沌回忆敌方以量子弱点为主。',
      color: '#DC2626',
      start_date: '2026-08-05',
      end_date: '2026-09-02',
      tags: ['混沌回忆', '高难'],
    },

    // === 绝区零 ===
    {
      id: 'sample-zzz-version',
      game: 'zenless-zone-zero',
      title: '「电子乱潮」1.3 版本',
      type: 'version-main',
      description: '全新剧情章节开放，新角色月城柳登场。',
      color: '#065F46',
      start_date: '2026-08-09',
      end_date: '2026-09-20',
      tags: ['版本更新', '月城柳'],
    },
    {
      id: 'sample-zzz-banner1',
      game: 'zenless-zone-zero',
      title: '「青雷残影」月城柳 + 苍角 UP',
      type: 'banner',
      description: '限定S级代理人「月城柳（电强攻）」+ A级「苍角」概率UP',
      color: '#7C3AED',
      start_date: '2026-08-09',
      end_date: '2026-08-30',
      tags: ['卡池', '月城柳'],
    },
    {
      id: 'sample-zzz-shinyu',
      game: 'zenless-zone-zero',
      title: '式舆防卫战·异变节点',
      type: 'challenge',
      description: '本期式舆防卫战以冰属性为优势属性。',
      color: '#B91C1C',
      start_date: '2026-08-16',
      end_date: '2026-09-13',
      tags: ['式舆防卫战', '高难'],
    },
    {
      id: 'sample-zzz-login',
      game: 'zenless-zone-zero',
      title: '「七日签到」登录福利',
      type: 'daily',
      description: '累计登录7天可领取加密母带 ×10。',
      color: '#0891B2',
      start_date: '2026-08-09',
      end_date: '2026-08-23',
      tags: ['签到', '福利'],
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

export function clearEventCache(): void {
  cachedEvents = null
}
