import { create } from 'zustand'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'
export const THEME_STORAGE_KEY = 'mtx-theme-preference'
const SYSTEM_QUERY = '(prefers-color-scheme: dark)'

export function normalizeThemePreference(value: unknown): ThemePreference {
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function resolveTheme(preference: ThemePreference, systemDark: boolean): ResolvedTheme {
  return preference === 'system' ? (systemDark ? 'dark' : 'light') : preference
}

function readPreference(): ThemePreference {
  try {
    return normalizeThemePreference(localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    return 'system'
  }
}

function systemIsDark() {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia(SYSTEM_QUERY).matches
}

function applyTheme(resolvedTheme: ResolvedTheme) {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = resolvedTheme
  document.documentElement.style.colorScheme = resolvedTheme
}

type ThemeState = {
  preference: ThemePreference
  resolvedTheme: ResolvedTheme
  setPreference: (preference: ThemePreference) => void
}

const initialPreference = readPreference()
export const useThemeStore = create<ThemeState>((set) => ({
  preference: initialPreference,
  resolvedTheme: resolveTheme(initialPreference, systemIsDark()),
  setPreference: (preference) => {
    const resolvedTheme = resolveTheme(preference, systemIsDark())
    try {
      localStorage.setItem(THEME_STORAGE_KEY, preference)
    } catch {
      // Storage may be disabled; the current tab can still switch themes.
    }
    applyTheme(resolvedTheme)
    set({ preference, resolvedTheme })
  },
}))

/** Provider owns subscriptions so StrictMode and unmounts never leak listeners. */
export function startThemeSync() {
  const media = window.matchMedia(SYSTEM_QUERY)
  const refresh = () => {
    const { preference } = useThemeStore.getState()
    const resolvedTheme = resolveTheme(preference, media.matches)
    applyTheme(resolvedTheme)
    useThemeStore.setState({ resolvedTheme })
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key !== null && event.key !== THEME_STORAGE_KEY) return
    useThemeStore.setState({ preference: normalizeThemePreference(event.newValue) })
    refresh()
  }
  refresh()
  media.addEventListener('change', refresh)
  window.addEventListener('storage', onStorage)
  return () => {
    media.removeEventListener('change', refresh)
    window.removeEventListener('storage', onStorage)
  }
}
