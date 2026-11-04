import type { Query, QueryClient, QueryKey } from '@tanstack/react-query'
import { ApiError } from '@/shared/api/request'

type PendingRefresh = { promise: Promise<void>; dirty: boolean }
const pendingRefreshes = new WeakMap<Query, PendingRefresh>()
const recoveryTimers = new WeakMap<Query, ReturnType<typeof setTimeout>>()
const FETCH_WAIT_MS = 5_000
const RECOVERY_WAIT_MS = 30_000

function scheduleRecovery(client: QueryClient, queryKey: QueryKey, query: Query) {
  if (!query.isActive() || recoveryTimers.has(query)) return
  const updateCount = query.state.dataUpdateCount
  const timer = setTimeout(() => {
    recoveryTimers.delete(query)
    if (client.getQueryCache().find({ queryKey, exact: true }) === query && query.isActive() && query.state.dataUpdateCount === updateCount) {
      void refreshRunQuery(client, queryKey)
    }
  }, RECOVERY_WAIT_MS)
  recoveryTimers.set(query, timer)
}

async function waitForFetch(fetch: Promise<unknown>): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timedOut = await Promise.race([
    fetch.then(() => false, () => false),
    new Promise<true>(resolve => { timer = setTimeout(() => resolve(true), FETCH_WAIT_MS) }),
  ])
  if (timer) clearTimeout(timer)
  return timedOut
}

/** Coalesce events while any snapshot is in flight, then fetch the newest state. */
export function refreshRunQuery(client: QueryClient, queryKey: QueryKey): Promise<void> {
  const query = client.getQueryCache().find({ queryKey, exact: true })
  if (query) {
    const recovery = recoveryTimers.get(query)
    if (recovery) {
      clearTimeout(recovery)
      recoveryTimers.delete(query)
    }
    const existing = pendingRefreshes.get(query)
    if (existing) {
      existing.dirty = true
      return existing.promise
    }
    const pending: PendingRefresh = { promise: Promise.resolve(), dirty: true }
    pendingRefreshes.set(query, pending)
    const refresh = (async () => {
      let failures = 0
      do {
        const inFlight = query.state.fetchStatus === 'fetching' ? query.promise : undefined
        if (inFlight) {
          const timedOut = await waitForFetch(inFlight)
          if (timedOut && query.promise === inFlight) {
            await client.cancelQueries({ queryKey, exact: true })
          }
        }
        // Events received before this request starts are covered by this snapshot.
        pending.dirty = false
        const request = client.invalidateQueries({ queryKey, exact: true })
        const activeFetch = query.state.fetchStatus === 'fetching' ? query.promise : undefined
        const timedOut = await waitForFetch(request)
        if (timedOut && activeFetch && query.promise === activeFetch) {
          await client.cancelQueries({ queryKey, exact: true })
        }
        const error = query.state.error
        const transientError = query.state.status === 'error' &&
          (!(error instanceof ApiError) || error.status === 429 || error.status >= 500)
        if (activeFetch && (timedOut || transientError) && query.isActive()) {
          failures += 1
          if (failures === 1) pending.dirty = true
          else if (!pending.dirty) scheduleRecovery(client, queryKey, query)
        } else {
          failures = 0
        }
        // Events received during the request need a later snapshot.
      } while (pending.dirty)
    })()
      .finally(() => pendingRefreshes.delete(query))
    pending.promise = refresh
    return refresh
  }
  return client.invalidateQueries({ queryKey, exact: true })
}
