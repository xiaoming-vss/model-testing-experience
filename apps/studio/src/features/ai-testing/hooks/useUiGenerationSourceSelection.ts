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
  const [profileVersionId, setProfileVersionIdState] = useState('')
  const [repositoryId, setRepositoryId] = useState('')
  const [commitMode, setCommitMode] = useState<UiGenerationSourceCommitMode>('profile')

  const versions = useMemo(() => options?.profileVersions ?? [], [options?.profileVersions])
  const versionIds = versions.map(item => item.versionId).join('|')
  const defaultProfileVersionId =
    options?.defaultProfileVersionId || versions[0]?.versionId || ''

  useEffect(() => {
    if (!versionIds) {
      if (profileVersionId) setProfileVersionIdState('')
      return
    }
    if (versionIds.split('|').includes(profileVersionId)) return
    setProfileVersionIdState(defaultProfileVersionId)
  }, [versionIds, defaultProfileVersionId, profileVersionId])

  const version = useMemo(
    () =>
      versions.find(item => item.versionId === profileVersionId) ??
      versions.find(item => item.versionId === defaultProfileVersionId) ??
      versions[0],
    [versions, profileVersionId, defaultProfileVersionId],
  )
  const frontendRepositoryIds = useMemo(
    () =>
      (version?.repositories ?? [])
        .filter(item => item.isFrontend || item.role === 'frontend' || item.role === 'fullstack')
        .map(item => item.repositoryId)
        .join('|'),
    [version],
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
      profileVersionId: version?.versionId ?? '',
      repositoryId,
      commitMode,
    }),
    [version?.versionId, repositoryId, commitMode],
  )
  const resolved = useMemo(
    () => resolveUiGenerationSource(options, selection),
    [options, selection],
  )

  return {
    selection,
    resolved,
    setProfileVersionId: (value: string) => {
      setProfileVersionIdState(value)
      setRepositoryId('')
    },
    setRepositoryId,
    setCommitMode,
  }
}
