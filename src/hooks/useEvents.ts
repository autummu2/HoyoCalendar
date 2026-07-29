import { useState, useEffect } from 'react'
import type { GameEvent } from '../types/events'
import { loadAllEvents } from '../lib/data-loader'

/**
 * 加载并缓存活动数据的 Hook
 * MVP 阶段从静态文件加载，返回全部活动列表
 */
export function useEvents() {
  const [events, setEvents] = useState<GameEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAllEvents()
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [])

  return { events, loading, error }
}
