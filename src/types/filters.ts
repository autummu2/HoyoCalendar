/** 筛选条件类型 */
export interface FilterState {
  /** 选中的游戏列表，空数组 = 全部 */
  games: string[]
  /** 选中的活动类型列表，空数组 = 全部 */
  eventTypes: string[]
  /** 是否只显示当前进行中的活动 */
  activeOnly: boolean
}

export const DEFAULT_FILTER: FilterState = {
  games: [],
  eventTypes: [],
  activeOnly: false,
}
