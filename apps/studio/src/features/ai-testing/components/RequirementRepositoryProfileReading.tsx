import { Empty } from 'antd'
import { RepositoryProfileReportView } from './RepositoryProfileReportView'
import type { RequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'

/** 仓库画像阅读态：正文只展示当前选中候选，标题与状态由页面标题栏承载。 */
export function RequirementRepositoryProfileReading({
  workspace,
}: {
  workspace: RequirementRepositoryProfileWorkspace
}) {
  const selectedProfileView = workspace.selectedProfileView
  return (
    <div className="gc-workspace">
      <div className="gc-reading-body">
        <div className="gc-artifact-scroll is-profile-reading">
          {workspace.candidateViewsLoading ? (
            <Empty description="正在读取画像候选" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : selectedProfileView?.profile ? (
            <RepositoryProfileReportView profile={selectedProfileView.profile} />
          ) : selectedProfileView?.resultYaml ? (
            <pre className="ai-task-code-block repository-profile-raw max-h-[60vh] overflow-auto">{selectedProfileView.resultYaml}</pre>
          ) : (
            <div className="gc-profile-reading-empty flex min-h-[320px] items-center justify-center">
              <Empty
                description="暂无可查看的画像候选"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
