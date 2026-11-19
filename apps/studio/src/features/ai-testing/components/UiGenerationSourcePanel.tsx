import { Button } from 'antd'
import { useState } from 'react'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import type { UiGenerationRunInputs, UiGenerationSourceInputs } from '../api/generationChain.api'
import { useUiGenerationSourceSelection } from '../hooks/useUiGenerationSourceSelection'
import { UiGenerationInputsModal } from './UiGenerationInputsModal'
import type { UiGenerationSourceOptionsState } from './UiGenerationSourceConfig'

export function UiGenerationSourcePanel({
  requirementId,
  projectId,
  sourceOptions,
  canWrite,
  busy,
  refreshInputs,
  configured,
  existingSource,
  snapshotLoading = false,
  onConfigure,
  onOpenProfile,
  onStart,
}: {
  requirementId: string
  projectId?: string
  sourceOptions: UiGenerationSourceOptionsState
  canWrite: boolean
  busy: boolean
  refreshInputs: boolean
  configured: boolean
  existingSource?: UiGenerationSourceInputs | null
  snapshotLoading?: boolean
  onConfigure: () => Promise<unknown>
  onOpenProfile?: () => void
  onStart: (inputs: UiGenerationRunInputs) => Promise<unknown>
}) {
  const [inputsOpen, setInputsOpen] = useState(false)
  const { resolved } = useUiGenerationSourceSelection(sourceOptions.data)
  const frozen = existingSource?.repository
  const repository = frozen ?? resolved.repository
  const profile = frozen
    ? (frozen.profileVersionNo ? `v${frozen.profileVersionNo}` : frozen.profileVersionId)
    : resolved.version?.label
  const needsProfile = !sourceOptions.loading && !sourceOptions.error
    && (resolved.blocker?.kind === 'no_profile_version' || resolved.blocker?.kind === 'no_frontend_repository')

  async function start(inputs: UiGenerationRunInputs) {
    if (!configured) await onConfigure()
    await onStart(inputs)
  }

  return (
    <section className="gc-inspector-section gc-inspector-source" aria-label="UI 测试生成摘要">
      <h3>{existingSource ? '当前生成来源' : '默认生成来源'}</h3>
      {snapshotLoading ? <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]" role="status">正在读取本次生成来源</p> : <dl className="ui-source-existing-list m-0 flex flex-col gap-2 [&>div]:grid [&>div]:grid-cols-[72px_minmax(0,1fr)] [&>div]:gap-2 [&_dd]:m-0 [&_dd]:min-w-0 [&_dd]:text-[11px] [&_dd]:[overflow-wrap:anywhere] [&_dt]:text-[11px] [&_dt]:text-[var(--app-surface-text-muted)]">
        <div><dt>画像版本</dt><dd>{profile || '未选择'}</dd></div>
        <div><dt>前端仓库</dt><dd>{repository?.pathWithNamespace || '未选择'}</dd></div>
        <div><dt>Commit</dt><dd title={repository?.commit}>{repository?.commit?.slice(0, 12) || '未选择'}</dd></div>
        <div><dt>功能用例</dt><dd>{existingSource ? `${existingSource.cases.length} 条` : '默认全选正式用例'}</dd></div>
      </dl>}
      {!existingSource && !snapshotLoading && sourceOptions.loading ? <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">正在读取仓库画像版本</p> : null}
      {!existingSource && sourceOptions.error ? <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">仓库画像读取失败，可在配置中重试。</p> : null}
      {needsProfile ? <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">{resolved.blocker?.title}</p> : null}
      {busy ? <p className="ui-source-note m-0 text-[11px] leading-[1.7] text-[var(--app-surface-text-muted)]">UI 测试运行中</p> : null}
      {canWrite ? (
        <div className="ui-source-summary-actions mt-3 flex flex-col gap-1.5">
          <ProjectActionButton projectId={projectId} action="execute" type="primary" disabled={busy} onClick={() => setInputsOpen(true)}>
            配置并生成
          </ProjectActionButton>
          {needsProfile && onOpenProfile ? <Button type="link" size="small" onClick={onOpenProfile}>去生成仓库画像</Button> : null}
        </div>
      ) : null}
      {inputsOpen && canWrite ? (
        <UiGenerationInputsModal
          requirementId={requirementId}
          refreshInputs={refreshInputs}
          sourceOptions={sourceOptions}
          busy={busy}
          onClose={() => setInputsOpen(false)}
          onOpenProfile={onOpenProfile}
          onSubmit={start}
        />
      ) : null}
    </section>
  )
}
