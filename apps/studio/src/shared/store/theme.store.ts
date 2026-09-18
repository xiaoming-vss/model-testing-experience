import { create } from 'zustand'

export const THEME_KEY = 'testpilot_theme_mode'

export type ThemeMode = 'light' | 'dark'

type ThemeState = {
  mode: ThemeMode
  setMode: (mode: ThemeMode) => void
  toggleMode: () => void
}

const getInitialMode = (): ThemeMode => {
  if (typeof window === 'undefined') return 'light'
  const stored = window.localStorage.getItem(THEME_KEY)
  return stored === 'dark' ? 'dark' : 'light'
}

export const useThemeStore = create<ThemeState>((set) => ({
  mode: getInitialMode(),
  setMode: (mode) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(THEME_KEY, mode)
    }
    set({ mode })
  },
  toggleMode: () =>
    set((state) => {
      const nextMode: ThemeMode = state.mode === 'dark' ? 'light' : 'dark'
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(THEME_KEY, nextMode)
      }
      return { mode: nextMode }
    }),
}))
