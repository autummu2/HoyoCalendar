import { useState, useEffect } from 'react'

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (raw != null) return JSON.parse(raw) as T
  } catch { /* ignore corrupt data */ }
  return fallback
}

/**
 * 和 useState 一样，但把状态持久化到 localStorage，刷新后恢复
 */
export function usePersistedState<T>(key: string, fallback: T) {
  const [state, setState] = useState<T>(() => load(key, fallback))

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state))
    } catch { /* storage may be unavailable */ }
  }, [key, state])

  return [state, setState] as const
}
