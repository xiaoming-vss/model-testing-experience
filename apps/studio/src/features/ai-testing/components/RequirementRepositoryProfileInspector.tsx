import { Alert, Button, Spin, Tag, Tooltip } from 'antd'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { getBindingRemoteName } from '@/features/base-services/utils/resourceBinding'
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
  const selectedInputVersion = workspace.understandingVersions.find(
    version => version.versionId === workspace.understandingVersionId,
  )
  const frozenUnderstanding = selectedVersion?.requirementUnderstandingVersion
  const understandingLabel = frozenUnderstanding?.versionNo
    ? `v${frozenUnderstanding.versionNo}`
    : selectedInputVersion?.label ?? '未记录'

  return (
    <div className="gc-profile-inspector">
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
          <p className="gc-inspector-hint">尚无画像版本。</p>
        )}
      </section>

      <section className="gc-inspector-section">
        <h3>上游追溯</h3>
        <div className="gc-inspector-trace">
          <span className="gc-trace-chip">需求理解<b>{understandingLabel}</b></span>
          <span className="gc-trace-chip">绑定仓库<b>{workspace.bindings.length} 个</b></span>
        </div>
        {workspace.bindings.length ? (
          <div className="gc-profile-binding-list">
            {workspace.bindings.map(binding => (
              <Tag key={binding.bindingId}>{getBindingRemoteName(binding)}</Tag>
            ))}
          </div>
        ) : !workspace.bindingsLoading ? (
          <p className="gc-inspector-hint">该需求未绑定代码仓库，请先在需求列表完成「代码绑定」。</p>
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
