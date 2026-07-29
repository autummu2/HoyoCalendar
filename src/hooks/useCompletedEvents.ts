import { useState, useCallback, useEffect } from 'react'

const STORAGE_KEY = 'hoyo-calendar-completed'

function loadCompleted(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const arr = JSON.parse(raw)
      if (Array.isArray(arr)) return new Set(arr)
    }
  } catch { /* ignore corrupt data */ }
  return new Set()
}

function saveCompleted(ids: Set<string>): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...ids]))
}

/**
 * 管理活动完成状态，持久化到 localStorage
 */
export function useCompletedEvents() {
  const [completedIds, setCompletedIds] = useState<Set<string>>(loadCompleted)

  useEffect(() => {
    saveCompleted(completedIds)
  }, [completedIds])

  const isCompleted = useCallback(
    (eventId: string) => completedIds.has(eventId),
    [completedIds],
  )

  const toggleComplete = useCallback((eventId: string) => {
    setCompletedIds((prev) => {
      const next = new Set(prev)
      if (next.has(eventId)) {
        next.delete(eventId)
      } else {
        next.add(eventId)
      }
      return next
    })
  }, [])

  return { completedIds, isCompleted, toggleComplete }
}
