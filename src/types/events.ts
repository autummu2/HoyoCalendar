import { z } from 'zod'

/** 支持的游戏 */
export const GameId = z.enum([
  'genshin-impact',
  'honkai-star-rail',
  'zenless-zone-zero',
  'tears-of-themis',
  'honkai-impact-3rd',
])

/** 活动类型 */
export const EventType = z.enum([
  'version-main',   // 版本主题活动
  'banner',         // 卡池/祈愿
  'daily',          // 签到/每日活动
  'challenge',      // 挑战/高难活动
  'web-event',      // 网页联动活动
  'festival',       // 节日/周年庆典
  'reward',         // 福利/兑换码
  'update',         // 版本更新
])

/** 活动子阶段 */
export const EventPhaseSchema = z.object({
  title: z.string().min(1),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
})

/** 活动条目 */
export const EventSchema = z.object({
  id: z.string().min(1),
  game: GameId,
  title: z.string().min(1),
  type: z.string().min(1),  // 允许自定义类型，EventType 枚举仅作参考
  description: z.string().optional(),
  start_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  end_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  /** 色条背景色（#RRGGBB），不指定则使用游戏品牌色 */
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/).optional(),
  /** 色条背景图片 URL，优先级高于 color。用于卡池立绘等 */
  bar_bg_image: z.string().optional(),
  banner_image: z.string().optional(),
  phases: z.array(EventPhaseSchema).optional(),
  tags: z.array(z.string()).optional(),
  source_url: z.string().url().optional(),
})

/** 活动数据文件结构 */
export const EventDataFileSchema = z.array(EventSchema)

// ===== TypeScript 类型推导 =====
export type Game = z.infer<typeof GameId>
export type EventTypeId = z.infer<typeof EventType>
export type EventPhase = z.infer<typeof EventPhaseSchema>
export type GameEvent = z.infer<typeof EventSchema>
export type EventDataFile = z.infer<typeof EventDataFileSchema>

// ===== 游戏元数据 =====
export interface GameInfo {
  id: Game
  name: string
  nameEn: string
  color: string
  accentColor: string
}

export const GAME_META: Record<Game, GameInfo> = {
  'genshin-impact': {
    id: 'genshin-impact',
    name: '原神',
    nameEn: 'Genshin Impact',
    color: '#4A90D9',
    accentColor: '#FFCC32',
  },
  'honkai-star-rail': {
    id: 'honkai-star-rail',
    name: '崩坏：星穹铁道',
    nameEn: 'Honkai: Star Rail',
    color: '#7B5EA7',
    accentColor: '#C4A8E0',
  },
  'zenless-zone-zero': {
    id: 'zenless-zone-zero',
    name: '绝区零',
    nameEn: 'Zenless Zone Zero',
    color: '#00E5A0',
    accentColor: '#66FFCC',
  },
  'tears-of-themis': {
    id: 'tears-of-themis',
    name: '未定事件簿',
    nameEn: 'Tears of Themis',
    color: '#D4929A',
    accentColor: '#F0C4CA',
  },
  'honkai-impact-3rd': {
    id: 'honkai-impact-3rd',
    name: '崩坏3',
    nameEn: 'Honkai Impact 3rd',
    color: '#FF6B9D',
    accentColor: '#FFB3CC',
  },
}

// ===== 活动类型元数据 =====
export interface EventTypeInfo {
  id: EventTypeId
  label: string
  icon: string
}

export const EVENT_TYPE_META: Record<EventTypeId, EventTypeInfo> = {
  'version-main': { id: 'version-main', label: '版本主题活动', icon: '🎭' },
  banner: { id: 'banner', label: '卡池/祈愿', icon: '🃏' },
  daily: { id: 'daily', label: '签到/每日', icon: '🎁' },
  challenge: { id: 'challenge', label: '挑战/高难', icon: '🏆' },
  'web-event': { id: 'web-event', label: '网页联动', icon: '🌐' },
  festival: { id: 'festival', label: '节日/周年', icon: '🎉' },
  reward: { id: 'reward', label: '福利/兑换码', icon: '📦' },
  update: { id: 'update', label: '版本更新', icon: '🔄' },
}
