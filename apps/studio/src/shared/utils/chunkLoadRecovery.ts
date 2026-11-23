const RELOAD_GUARD_KEY = 'mtx-chunk-reload-at'
const RELOAD_COOLDOWN_MS = 10_000

export type ChunkLoadRecoveryTarget = {
  addEventListener: (type: string, listener: EventListener) => void
  location: { reload: () => void }
  sessionStorage?: Pick<Storage, 'getItem' | 'setItem'>
}

/** 浏览器在动态 import 失败时给出的文案各不相同，统一识别为版本失效。 */
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? '')
  return /dynamically imported module|Importing a module script failed|Unable to preload CSS/i.test(message)
}

/**
 * 部署后旧 chunk 被删除时，动态 import 会失败并触发 vite:preloadError。
 * 自动刷新一次以拿到新版本；冷却窗口避免服务端持续失败时陷入刷新循环。
 */
export function installChunkLoadRecovery(target: ChunkLoadRecoveryTarget = window): void {
  target.addEventListener('vite:preloadError', () => {
    const now = Date.now()
    let last = 0
    try {
      last = Number(target.sessionStorage?.getItem(RELOAD_GUARD_KEY) ?? 0)
    } catch {
      // 隐私模式下 sessionStorage 可能抛错；忽略后仍尝试刷新一次。
    }
    if (Number.isFinite(last) && now - last < RELOAD_COOLDOWN_MS) return
    try {
      target.sessionStorage?.setItem(RELOAD_GUARD_KEY, String(now))
    } catch {
      // 无法持久化冷却时间时仍然刷新，避免用户停留在失效页面上。
    }
    target.location.reload()
  })
}
