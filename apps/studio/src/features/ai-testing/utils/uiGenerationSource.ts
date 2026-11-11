import type {
  UiGenerationSourceCommitMode,
  UiGenerationSourceOptions,
  UiGenerationSourceProfileVersion,
  UiGenerationSourceRepository,
} from '../api/generationChain.api'

export type UiGenerationSourceSelection = {
  profileVersionId: string
  repositoryId: string
  commitMode: UiGenerationSourceCommitMode
}

export type UiGenerationSourceBlocker = {
  kind:
    | 'no_profile_version'
    | 'no_frontend_repository'
    | 'repository_required'
    | 'repository_unavailable'
  title: string
  description?: string
  repositories: UiGenerationSourceRepository[]
}

export type ResolvedUiGenerationSource = {
  versions: UiGenerationSourceProfileVersion[]
  version?: UiGenerationSourceProfileVersion
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
 * Resolve the currently effective profile version and repository without inventing defaults.
 * The latest version comes from the API; a single frontend repository can be confirmed implicitly,
 * while multiple candidates stay unselected until the user chooses one.
 */
export function resolveUiGenerationSource(
  options: UiGenerationSourceOptions | undefined,
  selection: UiGenerationSourceSelection,
): ResolvedUiGenerationSource {
  const versions = options?.profileVersions ?? []
  const version =
    versions.find(item => item.versionId === selection.profileVersionId) ??
    versions.find(item => item.versionId === options?.defaultProfileVersionId) ??
    versions[0]
  const repositories = version?.repositories ?? []
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
    if (!versions.length) {
      return {
        kind: 'no_profile_version' as const,
        title: '尚未生成仓库画像',
        description: 'UI 生成需要成功的仓库画像版本。请先在需求分析分组运行仓库画像。',
        repositories,
      }
    }
    if (!frontendRepositories.length) {
      return {
        kind: 'no_frontend_repository' as const,
        title: '画像未识别出前端仓库',
        description:
          '该画像版本没有 frontend/fullstack 仓库。请检查需求代码绑定，或重新生成仓库画像。',
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
    versions,
    version,
    repositories,
    frontendRepositories,
    repository,
    recommendedRepositoryId,
    blocker,
    ready: Boolean(version && repository && !blocker),
  }
}
