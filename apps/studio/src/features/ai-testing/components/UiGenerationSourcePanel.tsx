import { Alert } from 'antd'
import { useState } from 'react'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { getErrorMessage } from '@/utils/format'
import type {
  UiGenerationRunInputs,
  UiGenerationSourceInputs,
} from '../api/generationChain.api'
import { useUiGenerationSourceSelection } from '../hooks/useUiGenerationSourceSelection'
import { UiGenerationCaseSelector } from './UiGenerationCaseSelector'
import {
  UiGenerationSourceConfig,
  type UiGenerationSourceOptionsState,
} from './UiGenerationSourceConfig'

/** UI 分组侧栏：确认仓库画像来源并启动首阶段；历史版本只展示冻结的来源信息。 */
export function UiGenerationSourcePanel({
  requirementId,
  sourceOptions,
  canWrite,
  busy,
  refreshInputs,
  configured,
  existingSource,
  onConfigure,
  onOpenProfile,
  onStart,
}: {
  requirementId: string
  sourceOptions: UiGenerationSourceOptionsState
  canWrite: boolean
  busy: boolean
  refreshInputs: boolean
  configured: boolean
  existingSource?: UiGenerationSourceInputs | null
  onConfigure: () => Promise<unknown>
  onOpenProfile?: () => void
  onStart: (inputs: UiGenerationRunInputs) => Promise<unknown>
}) {
  const [ids, setIds] = useState<string[] | undefined>()
  const [ready, setReady] = useState(false)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<unknown>()
  const { selection, resolved, setProfileVersionId, setRepositoryId, setCommitMode } =
    useUiGenerationSourceSelection(sourceOptions.data)
  const disabled = busy || starting
  const canStart = canWrite && !disabled && ready && Boolean(ids?.length) && resolved.ready

  async function start() {
    if (!canStart || !resolved.version || !resolved.repository || !ids?.length) return
    setStarting(true)
    setError(undefined)
    try {
      // 首次从 UI 分组启动时还没有任务壳，先按既有设置入口创建再运行。
      if (!configured) await onConfigure()
      await onStart({
        refreshInputs,
        functionCaseIds: ids,
        sourceProfileVersionId: resolved.version.versionId,
        sourceRepositoryId: resolved.repository.repositoryId,
        sourceCommitMode: selection.commitMode,
      })
    } catch (reason) {
      setError(reason)
    } finally {
      setStarting(false)
    }
  }

  const repository = existingSource?.repository

  return (
    <section className="gc-inspector-section gc-inspector-source" aria-label="UI 测试源码配置">
      <h3>源码仓库</h3>
      <p className="gc-inspector-hint">
        UI 生成使用仓库画像识别出的前端仓库，启动时冻结画像版本、分支和 commit。
      </p>
      <UiGenerationSourceConfig
        requirementId={requirementId}
        optionsState={sourceOptions}
        selection={selection}
        resolved={resolved}
        disabled={disabled}
        readOnly={!canWrite}
        caseSummary={
          <p className="ui-source-note">
            {resolved.ready
              ? '默认选中当前需求全部正式功能用例，可筛选调整。'
              : '选择画像版本与前端仓库后读取当前需求的正式功能用例。'}
          </p>
        }
        caseSelector={
          resolved.ready ? (
            <fieldset disabled={!canWrite || disabled} className="ui-source-cases-fieldset">
              <UiGenerationCaseSelector
                requirementId={requirementId}
                open
                value={ids}
                onChange={setIds}
                onReady={setReady}
              />
            </fieldset>
          ) : undefined
        }
        footer={
          canWrite ? (
            <div className="ui-source-start">
              <ProjectActionButton
                action="execute"
                operation="run"
                type="primary"
                loading={starting}
                disabled={!canStart}
                onClick={() => void start()}
              >
                开始生成
              </ProjectActionButton>
              {!resolved.ready ? null : !ids?.length ? (
                <p className="ui-source-note">请选择至少一条正式功能用例。</p>
              ) : null}
            </div>
          ) : (
            <p className="ui-source-note">只读成员可查看源码配置，不能启动生成。</p>
          )
        }
        onProfileVersionChange={setProfileVersionId}
        onRepositoryChange={setRepositoryId}
        onCommitModeChange={setCommitMode}
        onOpenProfile={onOpenProfile}
      />
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} /> : null}
      {existingSource ? (
        <div className="ui-source-existing">
          <h4>当前生成来源</h4>
          {repository ? (
            <dl className="ui-source-existing-list">
              <div><dt>仓库</dt><dd>{repository.pathWithNamespace}</dd></div>
              <div><dt>分支</dt><dd>{repository.branch || '未记录'}</dd></div>
              <div><dt>Commit</dt><dd>{repository.commit || '未记录'}</dd></div>
              <div><dt>画像版本</dt><dd>{repository.profileVersionNo ? `v${repository.profileVersionNo}` : repository.profileVersionId || '未记录'}</dd></div>
            </dl>
          ) : (
            <p className="ui-source-note">历史来源未记录仓库信息。</p>
          )}
        </div>
      ) : null}
    </section>
  )
}
