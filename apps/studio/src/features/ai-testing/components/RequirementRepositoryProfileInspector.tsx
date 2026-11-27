import { Alert, Button, Pagination, Popconfirm, Spin, Tag, Tooltip } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { getErrorMessage } from '@/utils/format'
import type { RequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'

/** 仓库画像阶段侧栏：查看候选和上游追溯；进入阅读区后在同一侧栏提供运行操作。 */
export function RequirementRepositoryProfileInspector({
  workspace,
  showRun = false,
}: {
  workspace: RequirementRepositoryProfileWorkspace
  showRun?: boolean
}) {
  const selectedProfileView = workspace.selectedProfileView
  const materialLabel = workspace.profileCandidateMode && selectedProfileView
    ? '已冻结，采用时核对'
    : selectedProfileView ? '未记录' : workspace.currentMaterialAvailable ? '当前已采用' : '未记录'

  return (
    <div className="gc-profile-inspector flex flex-col gap-[18px]">
      {workspace.personalLlm.dialog}
      {workspace.personalGitlab.dialog}

      <section className="gc-inspector-section">
        <h3>画像候选</h3>
        {<div>
          {workspace.currentProfileError ? <Alert showIcon type="error" title={`当前画像读取失败：${getErrorMessage(workspace.currentProfileError)}`} />
            : workspace.currentProfile?.candidateId ? <><Tag color="success">已采用</Tag><Button size="small" onClick={() => workspace.setSelectedCandidateId(workspace.currentProfile!.candidateId!)}>查看当前画像</Button></>
              : <Tag>尚未采用</Tag>}
        </div>}
        {workspace.candidateViewsError ? (
          <Alert
            showIcon
            type="error"
            title={getErrorMessage(workspace.candidateViewsError)}
            action={<Button size="small" onClick={workspace.refresh}>重试</Button>}
          />
        ) : workspace.candidateViewsLoading ? (
          <Spin size="small" />
        ) : workspace.candidateViews.length ? (
          <div className="gc-inspector-versions" role="group" aria-label="选择仓库画像候选">
            {workspace.candidateViews.map(version => (
              <button
                type="button"
                key={version.candidateId}
                className={`gc-version-button${workspace.selectedCandidateId === version.candidateId ? ' is-active' : ''}`}
                aria-pressed={workspace.selectedCandidateId === version.candidateId}
                onClick={() => workspace.setSelectedCandidateId(version.candidateId)}
              >
                {version.label}
                {version.candidateId === workspace.currentProfile?.candidateId ? '（当前）'
                    : workspace.candidateSummaries.find(item => item.candidateId === version.candidateId)?.disposition === 'rejected' ? '（已拒绝）' : ''}
              </button>
            ))}
          </div>
        ) : (
          <p className="gc-inspector-hint m-0 text-[12px] leading-[1.7] text-[var(--app-surface-text-muted)]">尚无画像候选。</p>
        )}
        {workspace.candidateTotal > workspace.candidatePageSize ? <Pagination size="small" current={workspace.candidatePage} pageSize={workspace.candidatePageSize} total={workspace.candidateTotal} showSizeChanger={false} onChange={workspace.setCandidatePage} /> : null}
        {workspace.selectedCandidate ? <div className="flex flex-wrap gap-2">
          {workspace.selectedCandidate.disposition === 'available' && !workspace.selectedCandidate.isCurrent ? <>
            <ProjectActionButton action="review" size="small" type="primary" loading={workspace.adopt.isPending} disabled={workspace.busy || !workspace.currentProfile || workspace.currentProfileLoading} onClick={() => workspace.adopt.mutate()}>采用此画像</ProjectActionButton>
            <Popconfirm title="拒绝这个画像候选？" onConfirm={() => workspace.dispose.mutate()}><ProjectActionButton action="write" size="small" disabled={workspace.busy}>拒绝</ProjectActionButton></Popconfirm>
          </> : null}
          {workspace.currentProfile?.candidateId ? <Popconfirm title="清空当前画像？" description="候选和已冻结的 UI 输入会保留。" onConfirm={() => workspace.clearCurrent.mutate()}><ProjectActionButton action="review" size="small" disabled={workspace.busy}>清空当前</ProjectActionButton></Popconfirm> : null}
        </div> : null}
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
