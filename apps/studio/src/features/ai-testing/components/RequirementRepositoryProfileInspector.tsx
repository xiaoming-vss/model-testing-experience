import { Alert, Button, Spin, Tag, Tooltip } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { getErrorMessage } from '@/utils/format'
import type { RequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'

/** 仓库画像阶段侧栏：查看版本和上游追溯；进入阅读区后在同一侧栏提供运行操作。 */
export function RequirementRepositoryProfileInspector({
  workspace,
  showRun = false,
}: {
  workspace: RequirementRepositoryProfileWorkspace
  showRun?: boolean
}) {
  const selectedVersion = workspace.selectedVersion
  const selectedInputVersion = workspace.materialVersions.find(
    version => version.versionId === workspace.materialVersionId,
  )
  const frozenMaterial = selectedVersion?.requirementMaterialVersion
  const materialLabel = frozenMaterial?.versionNo
    ? `v${frozenMaterial.versionNo}`
    : selectedInputVersion?.label ?? '未记录'

  return (
    <div className="gc-profile-inspector flex flex-col gap-[18px]">
      {workspace.personalLlm.dialog}
      {workspace.personalGitlab.dialog}

      <section className="gc-inspector-section">
        <h3>画像版本</h3>
        {workspace.versionsError ? (
          <Alert
            showIcon
            type="error"
            title={getErrorMessage(workspace.versionsError)}
            action={<Button size="small" onClick={workspace.refresh}>重试</Button>}
          />
        ) : workspace.versionsLoading ? (
          <Spin size="small" />
        ) : workspace.versions.length ? (
          <div className="gc-inspector-versions" role="group" aria-label="选择仓库画像版本">
            {workspace.versions.map(version => (
              <button
                type="button"
                key={version.versionId}
                className={`gc-version-button${workspace.selectedVersionId === version.versionId ? ' is-active' : ''}`}
                aria-pressed={workspace.selectedVersionId === version.versionId}
                onClick={() => workspace.setSelectedVersionId(version.versionId)}
              >
                {version.label}
                {version.versionId === workspace.latestVersion?.versionId ? '（最新）' : ''}
              </button>
            ))}
          </div>
        ) : (
          <p className="gc-inspector-hint m-0 text-[12px] leading-[1.7] text-[var(--app-surface-text-muted)]">尚无画像版本。</p>
        )}
      </section>

      <section className="gc-inspector-section">
        <h3>上游追溯</h3>
        <div className="gc-inspector-trace">
          <span className="gc-trace-chip">材料整理<b>{materialLabel}</b></span>
          <span className="gc-trace-chip">关联软件仓库<b>{workspace.bindings.length} 个</b></span>
        </div>
        {workspace.bindings.length ? (
          <div className="gc-profile-binding-list mt-2 flex flex-wrap gap-1">
            {workspace.bindings.map(binding => (
              <Tag key={binding.softwareRepositoryId}>
                {binding.softwareRepositoryName}
              </Tag>
            ))}
          </div>
        ) : !workspace.bindingsLoading ? (
          <p className="gc-inspector-hint m-0 text-[12px] leading-[1.7] text-[var(--app-surface-text-muted)]">
            该需求未关联软件仓库，请先在需求列表完成「软件仓库」关联。
          </p>
        ) : null}
      </section>

      {showRun ? (
        <section className="gc-inspector-section">
          <h3>运行</h3>
          <Tooltip title={workspace.runDisabledReason}>
            <span>
              <ProjectActionButton
                action="execute"
                operation={workspace.latestRun ? 'run' : 'create'}
                type="primary"
                loading={workspace.start.isPending}
                disabled={Boolean(workspace.runDisabledReason)}
                onClick={() => workspace.start.mutate()}
              >
                {workspace.latestRun ? '重新生成画像' : '生成画像'}
              </ProjectActionButton>
            </span>
          </Tooltip>
        </section>
      ) : null}
    </div>
  )
}
