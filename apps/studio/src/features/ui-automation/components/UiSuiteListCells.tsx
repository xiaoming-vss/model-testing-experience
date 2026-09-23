import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { DesktopOutlined } from '@ant-design/icons'
import { Popconfirm, Space, Tooltip, Typography } from 'antd'

const { Text } = Typography

/** 名称列：图标 + 名称。名称的字色由列表名称统一契约锁定（app/styles/listNameConsistency.test.ts），不要改。 */
export function UiSuiteNameCell({ name }: { name: string }) {
  return (
    <Space size={8} className="functional-suite-list-name ui-suite-list-name-cell">
      <span className="ui-suite-list-name-icon">
        <DesktopOutlined />
      </span>
      <Tooltip title={name}>
        <Text ellipsis>{name}</Text>
      </Tooltip>
    </Space>
  )
}

/** 所属迭代 / 需求：迭代是等宽色块，需求是普通文字。 */
export function UiSuiteScopeCell({ sprintName, requirementName }: { sprintName: string; requirementName: string }) {
  return (
    <Tooltip title={`${sprintName} / ${requirementName}`}>
      <span className="ui-suite-list-scope-cell">
        <span className="ui-suite-list-scope-chip">{sprintName}</span>
        <span className="ui-suite-list-scope-sep">/</span>
        <Text ellipsis>{requirementName}</Text>
      </span>
    </Tooltip>
  )
}

/** 操作列：运行 / 编辑 / 删除。图标按钮没有文字，无障碍名得给全。 */
export function UiSuiteRowActions({
  onRun,
  onEdit,
  onDelete,
  running,
  deleting,
}: {
  onRun: () => void
  onEdit: () => void
  onDelete: () => void
  running: boolean
  deleting: boolean
}) {
  return (
    <Space
      size={8}
      className="functional-suite-list-actions ui-suite-list-row-actions"
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <Tooltip title="运行测试集">
        <ProjectActionButton
          action="execute"
          type="text"
          shape="circle"
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
          aria-label="编辑 UI测试集"
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
            aria-label="删除 UI测试集"
            loading={deleting}
          />
        </Tooltip>
      </Popconfirm>
    </Space>
  )
}
