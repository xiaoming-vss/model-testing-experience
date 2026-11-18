import { Alert, Button, Spin, Tag } from 'antd'
import { useState } from 'react'
import { getErrorMessage } from '@/utils/format'
import {
  generationChainApi,
  type UiGenerationSourceCheck,
  type UiGenerationSourceCommitMode,
  type UiGenerationSourceOptions,
} from '../api/generationChain.api'
import { formatProfileConfidence, repositoryRoleMeta } from '../utils/repositoryProfileDisplay'
import type {
  ResolvedUiGenerationSource,
  UiGenerationSourceSelection,
} from '../utils/uiGenerationSource'

export type UiGenerationSourceOptionsState = {
  data?: UiGenerationSourceOptions
  loading: boolean
  error?: unknown
  reload?: () => void
}

export function UiGenerationSourceConfig({
  requirementId,
  optionsState,
  selection,
  resolved,
  disabled = false,
  onProfileVersionChange,
  onRepositoryChange,
  onCommitModeChange,
  onOpenProfile,
}: {
  requirementId: string
  optionsState: UiGenerationSourceOptionsState
  selection: UiGenerationSourceSelection
  resolved: ResolvedUiGenerationSource
  disabled?: boolean
  onProfileVersionChange: (versionId: string) => void
  onRepositoryChange: (repositoryId: string) => void
  onCommitModeChange: (mode: UiGenerationSourceCommitMode) => void
  onOpenProfile?: () => void
}) {
  const [checking, setChecking] = useState(false)
  const [checkedKey, setCheckedKey] = useState('')
  const [checkResult, setCheckResult] = useState<UiGenerationSourceCheck>()
  const [checkError, setCheckError] = useState<unknown>()

  const versionId = resolved.version?.versionId ?? ''
  const repositoryId = resolved.repository?.repositoryId ?? ''
  const checkKey = `${versionId}:${repositoryId}`
  const activeCheck = checkedKey === checkKey ? checkResult : undefined
  const activeCheckError = checkedKey === checkKey ? checkError : undefined

  async function runSourceCheck() {
    if (!versionId || !repositoryId || !resolved.repository?.commit || disabled) return
    setCheckedKey(checkKey)
    setChecking(true)
    setCheckResult(undefined)
    setCheckError(undefined)
    try {
      setCheckResult(
        await generationChainApi.uiSourceCheck(requirementId, {
          profileVersionId: versionId,
          repositoryId,
          pinnedCommit: resolved.repository?.commit ?? '',
        }),
      )
    } catch (reason) {
      setCheckError(reason)
    } finally {
      setChecking(false)
    }
  }

  if (optionsState.loading) {
    return (
      <div className="ui-source-config flex min-w-0 flex-col gap-3.5" aria-busy="true">
        <p className="ui-source-state m-0 flex items-center gap-2 text-[12px] text-[var(--app-surface-text-muted)]">
          <Spin size="small" /> 正在读取仓库画像版本
        </p>
      </div>
    )
  }

  if (optionsState.error) {
    return (
      <div className="ui-source-config flex min-w-0 flex-col gap-3.5">
        <Alert
          showIcon
          type="error"
          title={getErrorMessage(optionsState.error)}
          action={
            optionsState.reload ? (
              <Button size="small" onClick={optionsState.reload}>
                重试
              </Button>
            ) : undefined
          }
        />
      </div>
    )
  }

  const latestVersionId =
    optionsState.data?.defaultProfileVersionId || resolved.versions[0]?.versionId

  return (
    <div className="ui-source-config flex min-w-0 flex-col gap-3.5">
      {resolved.versions.length ? (
        <section className="ui-source-block flex min-w-0 flex-col gap-2" aria-label="画像版本">
          <h4 className="m-0 text-[12px] font-semibold">画像版本</h4>
          <div className="ui-source-version-list flex min-w-0 flex-wrap gap-1.5" role="group" aria-label="选择仓库画像版本">
            {resolved.versions.map(version => {
              const active = version.versionId === resolved.version?.versionId
              return (
                <button
                  type="button"
                  key={version.versionId}
                  className={`ui-source-version-button inline-flex min-h-[26px] cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] disabled:cursor-not-allowed disabled:opacity-60 ${active ? 'is-active border-[var(--app-accent-border)] bg-[var(--app-accent-surface)] font-semibold text-[var(--app-accent)]' : 'border-[var(--app-surface-border)] bg-[var(--app-surface)] text-[var(--app-surface-text)] hover:border-[var(--app-accent-border)] hover:text-[var(--app-accent)]'}`}
                  aria-pressed={active}
                  disabled={disabled}
                  onClick={() => onProfileVersionChange(version.versionId)}
                >
                  {version.label}
                  {version.versionId === latestVersionId ? (
                    <span className="ui-source-version-latest text-[10px] font-normal text-[var(--app-surface-text-muted)]">最新</span>
                  ) : null}
                </button>
              )
            })}
          </div>
          {resolved.version?.requirementMaterialVersion?.versionNo ? (
            <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">
              该画像使用材料整理 v
              {resolved.version.requirementMaterialVersion.versionNo}
            </p>
          ) : null}
        </section>
      ) : null}

      {resolved.blocker?.kind === 'no_profile_version' ? (
        <Alert
          showIcon
          type="warning"
          title={resolved.blocker.title}
          description={resolved.blocker.description}
          action={
            onOpenProfile ? (
              <Button size="small" disabled={disabled} onClick={onOpenProfile}>
                去生成仓库画像
              </Button>
            ) : undefined
          }
        />
      ) : null}

      {resolved.versions.length ? (
        <section className="ui-source-block flex min-w-0 flex-col gap-2" aria-label="前端仓库">
          <h4 className="m-0 text-[12px] font-semibold">前端仓库</h4>
          {resolved.blocker && resolved.blocker.kind !== 'no_profile_version' ? (
            <Alert
              showIcon
              type={resolved.blocker.kind === 'repository_unavailable' ? 'error' : 'warning'}
              title={resolved.blocker.title}
              description={resolved.blocker.description}
              action={
                onOpenProfile && resolved.blocker.kind === 'no_frontend_repository' ? (
                  <Button size="small" disabled={disabled} onClick={onOpenProfile}>
                    去生成仓库画像
                  </Button>
                ) : undefined
              }
            />
          ) : null}
          {resolved.frontendRepositories.length ? (
            <div className="ui-source-repo-list grid min-w-0 grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-2 max-[420.01px]:grid-cols-1" role="radiogroup" aria-label="选择前端仓库">
              {resolved.frontendRepositories.map(repository => {
                const role = repositoryRoleMeta(repository.role)
                const checked = resolved.repository?.repositoryId === repository.repositoryId
                const unavailable = !repository.available || Boolean(repository.profileError)
                return (
                  <label
                    key={repository.repositoryId}
                    className={`ui-source-repo-card flex min-w-0 cursor-pointer items-start gap-2 rounded-[10px] border p-2.5 [&_input]:mt-[3px] [&_input]:flex-none ${unavailable ? 'is-disabled cursor-not-allowed opacity-[0.72]' : checked ? 'is-selected border-[var(--app-accent-border)] bg-[var(--app-accent-surface)]' : 'border-[var(--app-surface-border)] bg-[var(--app-surface)] hover:border-[var(--app-accent-border)] hover:bg-[var(--app-surface-hover)]'}`}
                  >
                    <input
                      type="radio"
                      name={`ui-source-repository-${requirementId}`}
                      value={repository.repositoryId}
                      checked={checked}
                      disabled={disabled || unavailable}
                      aria-label={`选择仓库 ${repository.pathWithNamespace}`}
                      onChange={() => onRepositoryChange(repository.repositoryId)}
                    />
                    <span className="ui-source-repo-main flex min-w-0 flex-col gap-1">
                      <span className="ui-source-repo-title flex min-w-0 flex-wrap items-center gap-1 [&_.ant-tag]:m-0">
                        <strong className="min-w-0 text-[12px] [overflow-wrap:anywhere]">{repository.pathWithNamespace}</strong>
                        <Tag color={role.color}>{role.label}</Tag>
                        {repository.repositoryId === resolved.recommendedRepositoryId ? (
                          <Tag>推荐</Tag>
                        ) : null}
                      </span>
                      <span className="ui-source-repo-meta text-[11px] leading-[1.6] text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">
                        置信度 {formatProfileConfidence(repository.confidence)} · 分支{' '}
                        {repository.branch || '未记录'}
                      </span>
                      <span className="ui-source-repo-summary text-[12px] leading-[1.6] text-[var(--app-surface-text)] [overflow-wrap:anywhere]">
                        {repository.responsibilitySummary || '画像未记录职责摘要'}
                      </span>
                      {repository.keyPaths.length ? (
                        <span className="ui-source-repo-paths text-[11px] leading-[1.6] text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]">
                          {repository.keyPaths.join(' / ')}
                        </span>
                      ) : null}
                      {unavailable ? (
                        <span className="ui-source-repo-error text-[11px] leading-[1.6] text-[var(--app-profile-danger-text)] [overflow-wrap:anywhere]">
                          {repository.profileError || '该仓库当前不可用'}
                        </span>
                      ) : null}
                    </span>
                  </label>
                )
              })}
            </div>
          ) : (
            <ul className="ui-source-repo-all m-0 flex list-none flex-col gap-1 p-0 [&_.ant-tag]:m-0 [&_li]:flex [&_li]:min-w-0 [&_li]:items-center [&_li]:gap-1.5 [&_li]:text-[12px] [&_li]:[overflow-wrap:anywhere]" aria-label="画像仓库角色">
              {resolved.repositories.map(repository => (
                <li key={repository.repositoryId}>
                  <Tag color={repositoryRoleMeta(repository.role).color}>
                    {repositoryRoleMeta(repository.role).label}
                  </Tag>
                  <span>{repository.pathWithNamespace}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">
            整个仓库会作为三阶段共用的源码根，不裁剪子目录。
          </p>
        </section>
      ) : null}

      {resolved.version && resolved.frontendRepositories.length ? (
        <section className="ui-source-block flex min-w-0 flex-col gap-2" aria-label="Commit 模式">
          <h4 className="m-0 text-[12px] font-semibold">Commit 模式</h4>
          <div className="ui-source-commit-modes flex flex-wrap gap-x-3.5 gap-y-2" role="radiogroup" aria-label="选择 commit 模式">
            <label className="ui-source-commit-mode inline-flex cursor-pointer items-center gap-1.5 text-[12px] text-[var(--app-surface-text)]">
              <input
                type="radio"
                name={`ui-source-commit-mode-${requirementId}`}
                value="profile"
                checked={selection.commitMode === 'profile'}
                disabled={disabled}
                aria-label="使用画像 commit"
                onChange={() => onCommitModeChange('profile')}
              />
              使用画像 commit
            </label>
            <label className="ui-source-commit-mode inline-flex cursor-pointer items-center gap-1.5 text-[12px] text-[var(--app-surface-text)]">
              <input
                type="radio"
                name={`ui-source-commit-mode-${requirementId}`}
                value="latest"
                checked={selection.commitMode === 'latest'}
                disabled={disabled}
                aria-label="使用分支最新 HEAD"
                onChange={() => onCommitModeChange('latest')}
              />
              使用分支最新 HEAD
            </label>
          </div>
          {resolved.repository ? (
            <>
              <div className="ui-source-commit-detail flex min-w-0 flex-col gap-1 rounded-[8px] border border-[var(--app-surface-border)] bg-[var(--app-surface-hover)] px-2.5 py-2">
                {selection.commitMode === 'profile' ? (
                  <>
                    <p className="ui-source-commit-line m-0 flex flex-wrap items-baseline gap-1.5 text-[11px] [&>span]:text-[var(--app-surface-text-muted)] [&_code]:min-w-0 [&_code]:text-[11px] [&_code]:[overflow-wrap:anywhere]">
                      <span>commit</span>
                      <code>{resolved.repository.commit || '未记录'}</code>
                    </p>
                    <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">
                      启动时使用所选画像版本冻结的 commit，不再解析分支。
                    </p>
                  </>
                ) : (
                  <>
                    <p className="ui-source-commit-line m-0 flex flex-wrap items-baseline gap-1.5 text-[11px] [&>span]:text-[var(--app-surface-text-muted)] [&_code]:min-w-0 [&_code]:text-[11px] [&_code]:[overflow-wrap:anywhere]">
                      <span>分支</span>
                      <code>{resolved.repository.branch || '未记录'}</code>
                    </p>
                    <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">
                      启动时解析该分支最新 HEAD 并冻结为具体 commit；运行开始后分支前进不会改变本次源码。
                    </p>
                    {activeCheck ? (
                      <p className="ui-source-commit-line m-0 flex flex-wrap items-baseline gap-1.5 text-[11px] [&>span]:text-[var(--app-surface-text-muted)] [&_code]:min-w-0 [&_code]:text-[11px] [&_code]:[overflow-wrap:anywhere]">
                        <span>当前 HEAD</span>
                        <code>{activeCheck.currentCommit || '未记录'}</code>
                      </p>
                    ) : null}
                  </>
                )}
              </div>
              <div className="ui-source-check flex flex-col items-start gap-1.5">
                <Button
                  size="small"
                  loading={checking}
                  disabled={disabled || !resolved.ready || !resolved.repository.commit}
                  onClick={() => void runSourceCheck()}
                >
                  检查更新
                </Button>
                {activeCheckError ? (
                  <Alert showIcon type="error" title={getErrorMessage(activeCheckError)} />
                ) : null}
                {activeCheck?.changed ? (
                  <Alert
                    showIcon
                    type="warning"
                    title="分支已有新提交"
                    description={`当前 HEAD ${activeCheck.currentCommit} 与画像 commit ${activeCheck.pinnedCommit} 不同。可切换为「分支最新 HEAD」，或重新生成仓库画像。`}
                  />
                ) : activeCheck ? (
                  <Alert
                    showIcon
                    type="info"
                    title={`分支 ${activeCheck.branch || resolved.repository.branch} 的 HEAD 与所选 commit 一致`}
                    description={activeCheck.currentCommit || activeCheck.pinnedCommit}
                  />
                ) : null}
              </div>
            </>
          ) : null}
        </section>
      ) : null}

    </div>
  )
}
