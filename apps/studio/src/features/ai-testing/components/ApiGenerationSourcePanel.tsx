import { Alert, Button, Tag } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { getErrorMessage } from '@/utils/format'
import { aiTestingApi } from '../api/aiTesting.api'
import type { RepositoryProfileVersion } from '../types'
import { formatProfileConfidence, repositoryRoleMeta } from '../utils/repositoryProfileDisplay'
import { RequirementDesignConfigurationModal } from './RequirementDesignConfigurationModal'
import type { ApiSuggestedRepository } from './ApiInterfaceSelector'

const backendRoles = new Set(['backend', 'fullstack'])

/** 维护 API 测试当前选择的接口；接口来自接口库，仓库画像只提供后端仓库建议。 */
export function ApiGenerationSourcePanel({
  requirementId,
  projectId,
  taskId,
  canWrite,
  busy,
  profileVersion,
  profileLoading = false,
  onOpenProfile,
  onSaved,
}: {
  requirementId: string
  projectId: string
  taskId?: string
  canWrite: boolean
  busy: boolean
  profileVersion?: RepositoryProfileVersion | null
  profileLoading?: boolean
  onOpenProfile?: () => void
  onSaved: () => void
}) {
  const [open, setOpen] = useState(false)
  const client = useQueryClient()
  const task = useQuery({
    queryKey: ['apiGenerationInputTask', taskId],
    queryFn: () => aiTestingApi.getApiCaseGenerateTask(taskId!),
    enabled: Boolean(taskId),
    retry: false,
  })
  const count = task.data?.interfaceCount ?? task.data?.interfaceIds?.length ?? 0
  const backendRepositories = useMemo(
    () =>
      (profileVersion?.profile?.repositories ?? []).filter(repository =>
        backendRoles.has(repository.role),
      ),
    [profileVersion],
  )
  const recommendedRepositoryId = useMemo(
    () =>
      [...backendRepositories].sort(
        (left, right) => (right.confidence || 0) - (left.confidence || 0),
      )[0]?.repositoryId,
    [backendRepositories],
  )
  const suggestedRepositories: ApiSuggestedRepository[] = useMemo(
    () =>
      backendRepositories.map(repository => ({
        gitRepositoryId: repository.repositoryId,
        pathWithNamespace: repository.pathWithNamespace,
      })),
    [backendRepositories],
  )
  const profileLabel = profileVersion
    ? profileVersion.label || `v${profileVersion.versionNo}`
    : ''
  return (
    <>
      <section className="gc-inspector-section gc-inspector-source" aria-label="API 测试建议后端仓库">
        <h3>建议的后端仓库</h3>
        {profileLoading ? (
          <p className="gc-inspector-summary">正在读取仓库画像...</p>
        ) : profileVersion ? (
          backendRepositories.length ? (
            <>
              <p className="gc-inspector-summary">
                来自仓库画像 {profileLabel}。建议仅用于筛选接口，生成时仍可选择其他软件仓库。
              </p>
              <ul className="api-source-repo-list m-0 grid list-none gap-1.5 p-0 min-w-0" aria-label="画像建议的后端仓库">
                {backendRepositories.map(repository => {
                  const role = repositoryRoleMeta(repository.role)
                  return (
                    <li key={repository.repositoryId} className="api-source-repo grid min-w-0 gap-[3px] rounded-lg border border-[var(--app-surface-border)] bg-[var(--app-surface)] p-[8px_10px]">
                      <span className="api-source-repo-title flex min-w-0 flex-wrap items-center gap-1.5">
                        <strong className="[overflow-wrap:anywhere]">{repository.pathWithNamespace}</strong>
                        <Tag color={role.color}>{role.label}</Tag>
                        {repository.repositoryId === recommendedRepositoryId ? (
                          <Tag>推荐</Tag>
                        ) : null}
                      </span>
                      <span className="api-source-repo-meta text-xs leading-normal text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">
                        置信度 {formatProfileConfidence(repository.confidence)}
                      </span>
                      {repository.responsibilitySummary ? (
                        <span className="api-source-repo-meta text-xs leading-normal text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">
                          {repository.responsibilitySummary}
                        </span>
                      ) : null}
                      {repository.keyPaths.length ? (
                        <span className="api-source-repo-paths text-xs leading-normal text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">
                          {repository.keyPaths.join(' / ')}
                        </span>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </>
          ) : (
            <p className="gc-inspector-summary">
              仓库画像未识别出后端仓库；接口仍可从接口库任意选择。
            </p>
          )
        ) : (
          <p className="gc-inspector-summary">
            尚未生成仓库画像。接口仍可从接口库任意选择；生成画像后可获得后端仓库建议。
          </p>
        )}
        {!profileVersion && !profileLoading && onOpenProfile ? (
          <Button type="link" size="small" onClick={onOpenProfile}>
            去生成仓库画像
          </Button>
        ) : null}
      </section>
      <section className="gc-inspector-section gc-inspector-source" aria-label="API 测试接口">
        <h3>接口来源</h3>
        <p>
          {task.isFetching
            ? '正在读取接口'
            : count
              ? `已选择 ${count} 个接口`
              : '尚未选择接口'}
        </p>
        {canWrite || count ? (
          <Button
            size="small"
            disabled={
              task.isFetching || Boolean(task.error) || (canWrite && busy)
            }
            onClick={() => setOpen(true)}
          >
            {canWrite ? (count ? '查看 / 修改接口' : '选择接口') : '查看接口'}
          </Button>
        ) : null}
        {task.error ? (
          <Alert
            showIcon
            type="error"
            title={getErrorMessage(task.error)}
            action={
              <Button size="small" onClick={() => void task.refetch()}>
                重试读取
              </Button>
            }
          />
        ) : null}
        <p className="gc-inspector-summary">生成时读取所选接口的最新定义。</p>
        {open ? (
          <RequirementDesignConfigurationModal
            requirementId={requirementId}
            projectId={projectId}
            kind="api"
            tasks={[]}
            initialTaskId={taskId}
            readOnly={!canWrite}
            suggestedRepositories={suggestedRepositories}
            onClose={() => setOpen(false)}
            onSaved={() => {
              setOpen(false)
              void client.invalidateQueries({ queryKey: ['apiGenerationInputTask'] })
              void client.invalidateQueries({
                queryKey: ['requirementDesignConfiguration', 'api'],
              })
              onSaved()
            }}
          />
        ) : null}
      </section>
    </>
  )
}
