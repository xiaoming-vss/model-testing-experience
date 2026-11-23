import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isChunkLoadError, installChunkLoadRecovery } from './chunkLoadRecovery'

function createTarget() {
  const listeners = new Map<string, EventListener>()
  const stored = new Map<string, string>()
  const reload = vi.fn()
  return {
    target: {
      addEventListener: (type: string, listener: EventListener) => { listeners.set(type, listener) },
      location: { reload },
      sessionStorage: {
        getItem: (key: string) => stored.get(key) ?? null,
        setItem: (key: string, value: string) => { stored.set(key, value) },
      },
    },
    emit: () => listeners.get('vite:preloadError')?.(new Event('vite:preloadError')),
    reload,
  }
}

describe('installChunkLoadRecovery', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reloads once for a stale chunk and suppresses duplicates within the cooldown', () => {
    const { target, emit, reload } = createTarget()
    installChunkLoadRecovery(target)

    emit()
    emit()

    expect(reload).toHaveBeenCalledTimes(1)

    vi.setSystemTime(new Date('2026-01-01T00:00:11Z'))
    emit()

    expect(reload).toHaveBeenCalledTimes(2)
  })

  it('still reloads when sessionStorage is unavailable', () => {
    const reload = vi.fn()
    let listener: EventListener | undefined
    installChunkLoadRecovery({
      addEventListener: (_type, next) => { listener = next },
      location: { reload },
      sessionStorage: {
        getItem: () => { throw new Error('storage disabled') },
        setItem: () => { throw new Error('storage disabled') },
      },
    })

    listener?.(new Event('vite:preloadError'))

    expect(reload).toHaveBeenCalledTimes(1)
  })
})

describe('isChunkLoadError', () => {
  it('recognizes stale chunk failures across browsers', () => {
    expect(isChunkLoadError(new Error('Failed to fetch dynamically imported module: https://example.test/a.js'))).toBe(true)
    expect(isChunkLoadError(new Error('error loading dynamically imported module'))).toBe(true)
    expect(isChunkLoadError(new Error('Importing a module script failed.'))).toBe(true)
    expect(isChunkLoadError(new Error('Unable to preload CSS for /assets/a.css'))).toBe(true)
  })

  it('does not treat ordinary render errors as chunk failures', () => {
    expect(isChunkLoadError(new Error('render exploded'))).toBe(false)
    expect(isChunkLoadError(null)).toBe(false)
  })
})
