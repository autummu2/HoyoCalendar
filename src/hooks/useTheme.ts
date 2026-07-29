import { useState, useEffect, useCallback } from 'react'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'hoyo-calendar-theme'

function getSystemTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return getSystemTheme()
}

export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme)

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    localStorage.setItem(STORAGE_KEY, t)
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const next = prev === 'light' ? 'dark' : 'light'
      localStorage.setItem(STORAGE_KEY, next)
      return next
    })
  }, [])

  // Apply theme class to <html>
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', theme === 'dark')
  }, [theme])

  // Listen for system theme changes when no explicit preference
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) {
        setThemeState(e.matches ? 'dark' : 'light')
      }
    }
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return { theme, setTheme, toggleTheme }
}
