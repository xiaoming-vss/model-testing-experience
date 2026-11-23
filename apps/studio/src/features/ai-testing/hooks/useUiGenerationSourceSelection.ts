import { useEffect, useMemo, useState } from 'react'
import type {
  UiGenerationSourceCommitMode,
  UiGenerationSourceOptions,
} from '../api/generationChain.api'
import {
  resolveUiGenerationSource,
  type UiGenerationSourceSelection,
} from '../utils/uiGenerationSource'

/** Owns the source selection shared by the UI group inspector and the first-run input modal. */
export function useUiGenerationSourceSelection(options?: UiGenerationSourceOptions) {
  const [repositoryId, setRepositoryId] = useState('')
  const [commitMode, setCommitMode] = useState<UiGenerationSourceCommitMode>('profile')
  const profile = options?.currentProfile ?? undefined

  const frontendRepositoryIds = useMemo(
    () =>
      (profile?.repositories ?? [])
        .filter(item => item.isFrontend || item.role === 'frontend' || item.role === 'fullstack')
        .map(item => item.repositoryId)
        .join('|'),
    [profile],
  )

  useEffect(() => {
    const ids = frontendRepositoryIds ? frontendRepositoryIds.split('|') : []
    if (!ids.length) {
      if (repositoryId) setRepositoryId('')
      return
    }
    if (ids.includes(repositoryId)) return
    setRepositoryId(ids.length === 1 ? ids[0] : '')
  }, [frontendRepositoryIds, repositoryId])

  const selection: UiGenerationSourceSelection = useMemo(
    () => ({
      repositoryId,
      commitMode,
    }),
    [repositoryId, commitMode],
  )
  const resolved = useMemo(
    () => resolveUiGenerationSource(options, selection),
    [options, selection],
  )

  return {
    selection,
    resolved,
    setRepositoryId,
    setCommitMode,
  }
}
