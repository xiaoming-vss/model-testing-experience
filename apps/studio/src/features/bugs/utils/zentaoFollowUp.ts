export type ZentaoFollowUp = { actor: string | null; jobId: string; requestId: string; started: boolean }

function key(actor: string, bugId: string) {
  return `mtx:zentao-follow-up:${encodeURIComponent(actor)}:${encodeURIComponent(bugId)}`
}

export function readFollowUp(actor: string | null, bugId: string): ZentaoFollowUp | null {
  if (!actor) return null
  try {
    const value: unknown = JSON.parse(sessionStorage.getItem(key(actor, bugId)) ?? 'null')
    if (!value || typeof value !== 'object' || !('jobId' in value) || !('requestId' in value)) return null
    if (typeof value.jobId !== 'string' || typeof value.requestId !== 'string'
      || !/^[A-Za-z0-9_.:-]{1,128}$/.test(value.jobId)
      || !/^[A-Za-z0-9_.:-]{1,128}$/.test(value.requestId)) return null
    return { actor, jobId: value.jobId, requestId: value.requestId, started: false }
  } catch { return null }
}

export function saveFollowUp(actor: string | null, bugId: string, value: ZentaoFollowUp | null) {
  if (!actor) return
  try {
    if (value) sessionStorage.setItem(key(actor, bugId), JSON.stringify({ jobId: value.jobId, requestId: value.requestId }))
    else sessionStorage.removeItem(key(actor, bugId))
  } catch { /* A disabled session store does not prevent the accepted job from running. */ }
}
