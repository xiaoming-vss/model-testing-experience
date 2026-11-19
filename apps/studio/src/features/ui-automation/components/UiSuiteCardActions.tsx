import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { Popconfirm, Tooltip } from 'antd'

/** 卡片操作组：运行 / 编辑 / 删除。卡片容器负责阻止点击冒泡，这里只渲染按钮。 */
export function UiSuiteCardActions({
  onRun,
  onEdit,
  onDelete,
  running,
  runDisabled = false,
  deleting,
}: {
  onRun: () => void
  onEdit: () => void
  onDelete: () => void
  running: boolean
  runDisabled?: boolean
  deleting: boolean
}) {
  return (
    <>
      <Tooltip title={runDisabled ? '请先在工具栏选择 UI 环境' : '运行测试集'}>
        <ProjectActionButton
          action="execute"
          type="text"
          shape="circle"
          disabled={runDisabled}
          className="action-btn-read"
          operation="run"
          iconOnly
          aria-label="运行 UI测试集"
          loading={running}
          onClick={onRun}
        />
      </Tooltip>
      <Tooltip title="编辑测试集">
        <ProjectActionButton
          action="write"
          type="text"
          shape="circle"
          className="action-btn-update"
          operation="edit"
          iconOnly
          aria-label="编辑测试集"
          onClick={onEdit}
        />
      </Tooltip>
      <Popconfirm title="确认删除该 UI测试集？" onConfirm={onDelete}>
        <Tooltip title="删除测试集">
          <ProjectActionButton
            action="write"
            danger
            type="text"
            shape="circle"
            className="action-btn-delete"
            operation="delete"
            iconOnly
            aria-label="删除测试集"
            loading={deleting}
          />
        </Tooltip>
      </Popconfirm>
    </>
  )
}
