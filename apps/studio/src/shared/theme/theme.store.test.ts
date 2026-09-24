import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import bootstrapHtml from '../../../index.html?raw'
import { normalizeThemePreference, resolveTheme, startThemeSync, THEME_STORAGE_KEY, useThemeStore } from './theme.store'

let systemDark = false
let listeners: Set<() => void>
let stop: (() => void) | undefined

beforeEach(() => {
  localStorage.clear()
  systemDark = false
  listeners = new Set()
  vi.stubGlobal('matchMedia', vi.fn(() => ({
    get matches() { return systemDark },
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  })))
  useThemeStore.setState({ preference: 'system', resolvedTheme: 'light' })
})

afterEach(() => {
  stop?.()
  stop = undefined
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
  delete document.documentElement.dataset.theme
  document.documentElement.style.colorScheme = ''
})

function changeSystem(dark: boolean) {
  systemDark = dark
  listeners.forEach((listener) => listener())
}

describe('theme preference lifecycle', () => {
  it('follows system changes only while system is selected and persists explicit choices', () => {
    stop = startThemeSync()
    changeSystem(true)
    expect(document.documentElement.dataset.theme).toBe('dark')
    useThemeStore.getState().setPreference('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    changeSystem(false)
    changeSystem(true)
    expect(useThemeStore.getState().resolvedTheme).toBe('light')
    useThemeStore.getState().setPreference('system')
    expect(document.documentElement.style.colorScheme).toBe('dark')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
  })

  it('synchronizes other tabs, handles removal and ignores unrelated storage', () => {
    stop = startThemeSync()
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'dark' }))
    expect(useThemeStore.getState().resolvedTheme).toBe('dark')
    window.dispatchEvent(new StorageEvent('storage', { key: 'unrelated', newValue: 'light' }))
    expect(useThemeStore.getState().preference).toBe('dark')
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: null }))
    expect(useThemeStore.getState().preference).toBe('system')
    expect(useThemeStore.getState().resolvedTheme).toBe('light')
  })

  it('keeps switching usable when browser storage is blocked', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    useThemeStore.getState().setPreference('dark')
    expect(document.documentElement.dataset.theme).toBe('dark')
  })

  it('cleans up subscriptions across provider remounts', () => {
    stop = startThemeSync()
    expect(listeners.size).toBe(1)
    stop()
    expect(listeners.size).toBe(0)
    window.dispatchEvent(new StorageEvent('storage', { key: THEME_STORAGE_KEY, newValue: 'dark' }))
    expect(useThemeStore.getState().preference).toBe('system')
    stop = startThemeSync()
    expect(listeners.size).toBe(1)
  })
})

describe('first paint bootstrap', () => {
  const script = bootstrapHtml.match(/<script>([\s\S]*?)<\/script>/)?.[1]
  it.each([null, 'light', 'dark', 'system', 'invalid'])('agrees with the store for saved preference %s', (saved) => {
    expect(script).toBeTruthy()
    for (const dark of [false, true]) {
      const root = { dataset: { theme: '' }, style: { colorScheme: '' } }
      new Function('localStorage', 'window', 'document', script!)(
        { getItem: () => saved }, { matchMedia: () => ({ matches: dark }) }, { documentElement: root },
      )
      expect(root.dataset.theme).toBe(resolveTheme(normalizeThemePreference(saved), dark))
      expect(root.style.colorScheme).toBe(root.dataset.theme)
    }
  })

  it('uses the system theme when storage cannot be read', () => {
    const root = { dataset: { theme: '' }, style: { colorScheme: '' } }
    new Function('localStorage', 'window', 'document', script!)(
      { getItem: () => { throw new Error('blocked') } },
      { matchMedia: () => ({ matches: true }) }, { documentElement: root },
    )
    expect(root.dataset.theme).toBe('dark')
  })
})
