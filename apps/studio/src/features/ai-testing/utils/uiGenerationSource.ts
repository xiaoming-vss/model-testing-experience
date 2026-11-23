import type {
  UiGenerationSourceCommitMode,
  UiGenerationSourceOptions,
  UiGenerationSourceCurrentProfile,
  UiGenerationSourceRepository,
} from '../api/generationChain.api'

export type UiGenerationSourceSelection = {
  repositoryId: string
  commitMode: UiGenerationSourceCommitMode
}

export type UiGenerationSourceBlocker = {
  kind:
    | 'no_profile'
    | 'no_frontend_repository'
    | 'repository_required'
    | 'repository_unavailable'
  title: string
  description?: string
  repositories: UiGenerationSourceRepository[]
}

export type ResolvedUiGenerationSource = {
  profile?: UiGenerationSourceCurrentProfile
  repositories: UiGenerationSourceRepository[]
  frontendRepositories: UiGenerationSourceRepository[]
  repository?: UiGenerationSourceRepository
  recommendedRepositoryId?: string
  blocker?: UiGenerationSourceBlocker
  ready: boolean
}

/** A repository is usable UI source when either the profile flags it or its role is frontend/fullstack. */
export function isFrontendRepository(repository: UiGenerationSourceRepository) {
  return (
    repository.isFrontend ||
    repository.role === 'frontend' ||
    repository.role === 'fullstack'
  )
}

/**
 * Resolve the current profile and repository without inventing defaults.
 * A single frontend repository can be confirmed implicitly,
 * while multiple candidates stay unselected until the user chooses one.
 */
export function resolveUiGenerationSource(
  options: UiGenerationSourceOptions | undefined,
  selection: UiGenerationSourceSelection,
): ResolvedUiGenerationSource {
  const profile = options?.currentProfile ?? undefined
  const repositories = profile?.repositories ?? []
  const frontendRepositories = repositories.filter(isFrontendRepository)
  const repository =
    frontendRepositories.find(item => item.repositoryId === selection.repositoryId) ??
    (frontendRepositories.length === 1 ? frontendRepositories[0] : undefined)
  const availableRepositories = frontendRepositories.filter(
    item => item.available && !item.profileError,
  )
  const recommendedRepositoryId = [...(availableRepositories.length ? availableRepositories : frontendRepositories)].sort(
    (left, right) => (right.confidence || 0) - (left.confidence || 0),
  )[0]?.repositoryId

  const blocker = (() => {
    if (!profile) {
      return {
        kind: 'no_profile' as const,
        title: '尚未采用仓库画像',
        description: '请先生成并采用一份仓库画像。',
        repositories,
      }
    }
    if (!frontendRepositories.length) {
      return {
        kind: 'no_frontend_repository' as const,
        title: '画像未识别出前端仓库',
        description:
          '当前画像没有 frontend/fullstack 仓库。请检查需求关联的软件仓库，或重新生成仓库画像。',
        repositories,
      }
    }
    if (!repository) {
      return {
        kind: 'repository_required' as const,
        title: `检测到 ${frontendRepositories.length} 个前端仓库`,
        description: '一次 UI 生成只使用一个源码根，请选择要使用的仓库。',
        repositories,
      }
    }
    if (!repository.available) {
      return {
        kind: 'repository_unavailable' as const,
        title: '所选仓库当前不可用',
        description:
          repository.profileError ||
          '画像未记录可用的分支或 commit，请重新生成仓库画像后重试。',
        repositories,
      }
    }
    return undefined
  })()

  return {
    profile,
    repositories,
    frontendRepositories,
    repository,
    recommendedRepositoryId,
    blocker,
    ready: Boolean(profile && repository && !blocker),
  }
}
