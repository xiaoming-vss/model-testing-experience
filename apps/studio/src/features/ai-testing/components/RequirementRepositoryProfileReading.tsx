import { Empty } from 'antd'
import { RepositoryProfileReportView } from './RepositoryProfileReportView'
import type { RequirementRepositoryProfileWorkspace } from '../hooks/useRequirementRepositoryProfileWorkspace'

/** 仓库画像阅读态：正文只展示当前选中版本，标题与状态由页面标题栏承载。 */
export function RequirementRepositoryProfileReading({
  workspace,
}: {
  workspace: RequirementRepositoryProfileWorkspace
}) {
  const selectedVersion = workspace.selectedVersion
  return (
    <div className="gc-workspace">
      <div className="gc-reading-body">
        <div className="gc-artifact-scroll is-profile-reading">
          {workspace.versionsLoading ? (
            <Empty description="正在读取画像版本" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : selectedVersion?.profile ? (
            <RepositoryProfileReportView profile={selectedVersion.profile} />
          ) : selectedVersion?.resultYaml ? (
            <pre className="ai-task-code-block repository-profile-raw">{selectedVersion.resultYaml}</pre>
          ) : (
            <div className="gc-profile-reading-empty">
              <Empty
                description="仓库画像分析 skill 尚未接入，暂无可展示内容"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
