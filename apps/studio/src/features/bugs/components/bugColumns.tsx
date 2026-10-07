import { Space, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { Link } from 'react-router-dom'
import { AppIcon } from '@/shared/icons'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { pickCreatedAt, formatTime, pickUpdatedAt } from '@/utils/format'
import type { Bug, BugAction } from '../types'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS, getBugStateLabel, getBugActions,
  getBugPriorityTone, getBugStatusTone, getBugActionLabel } from '../utils/bugMeta'
const { Text } = Typography

export function bugColumns({ memberNameMap, sprintNameMap, onTransition, optionalColumns }: {
  optionalColumns: string[]
  memberNameMap: Map<string, string>; sprintNameMap: Map<string, string>
  onTransition: (bug: Bug, action: BugAction) => void
}): NonNullable<TableProps<Bug>['columns']> {
  const columns: NonNullable<TableProps<Bug>['columns']> = [
    { title: 'ID', key: 'id', width: 100, render: (_, bug) => <span className="bug-list-number">{bug.id}</span> },
    { title: 'Bug 标题', key: 'title', width: 280,
      render: (_, bug) => <Space size={8} className="functional-suite-list-name bug-title-cell">
        <span className="bug-name-icon"><AppIcon name="bug" size={14} /></span>
        <Tooltip title={bug.title}><Link className="ant-typography bug-title-text" to={`/bugs/${bug.bugId}`}>{bug.title}</Link></Tooltip>
      </Space> },
    { title: '状态', key: 'status', width: 110, align: 'center',
      render: (_, bug) => <span className={`bug-status-pill tone-${getBugStatusTone(bug.status)}`}>
        <span className="bug-status-dot" />{getBugStateLabel(bug)}</span> },
    { title: '严重程度', key: 'severity', width: 110, align: 'center',
      render: (_, bug) => <Text className="bug-muted-cell">{BUG_SEVERITY_LABELS[bug.severity] ?? bug.severity}</Text> },
    { title: '优先级', key: 'priority', width: 80, align: 'center',
      render: (_, bug) => <span className={`bug-priority-chip tone-${getBugPriorityTone(bug.priority)}`}>
        {BUG_PRIORITY_LABELS[bug.priority] ?? bug.priority}</span> },
    { title: '创建人', key: 'reporter', width: 100, ellipsis: true,
      render: (_, bug) => memberNameMap.get(bug.reporterUserId) ?? bug.reporterUserId },
    { title: '责任人', key: 'assignee', width: 100, ellipsis: true,
      render: (_, bug) => memberNameMap.get(bug.assigneeUserId) ?? bug.assigneeUserId },
    { title: '发现迭代', key: 'foundSprint', width: 130, ellipsis: true,
      render: (_, bug) => sprintNameMap.get(bug.foundSprintId) ?? '未关联' },
    { title: '计划修复迭代', key: 'plannedFixSprint', width: 130, ellipsis: true,
      render: (_, bug) => bug.plannedFixSprintId ? sprintNameMap.get(bug.plannedFixSprintId) ?? '未关联' : '未安排' },
    { title: '更新时间', key: 'updatedAt', width: 160,
      render: (_, bug) => <Text className="bug-time-cell" type="secondary">{formatTime(pickUpdatedAt(bug))}</Text> },
  ]
  const optional: NonNullable<TableProps<Bug>['columns']> = [
    { key: 'requirement', title: '所属需求', width: 180, ellipsis: true,
      render: (_, bug) => bug.requirementName || '未关联需求' },
    { key: 'createdAt', title: '创建时间', width: 160, render: (_, bug) => formatTime(pickCreatedAt(bug)) },
    { key: 'order', title: '关联测试单', width: 180, ellipsis: true,
      render: (_, bug) => bug.sourceOrderName || '未关联测试单' },
    { key: 'case', title: '关联用例', width: 180, ellipsis: true,
      render: (_, bug) => bug.sourceCaseTitle || '未关联用例' },
  ]
  columns.push(...optional.filter((column) => optionalColumns.includes(String(column.key))))
  columns.push({ title: '操作', key: 'actions', width: 200, align: 'right', fixed: 'right',
    render: (_, bug) => <Space size={8} className="bug-row-actions" onClick={(event) => event.stopPropagation()}>
      {(getBugActions(bug)).map((action) => (
        <ProjectActionButton key={action} action="bug_handle" type="text" size="small"
          danger={action === 'activate'} onClick={() => onTransition(bug, action)}>
          {getBugActionLabel(action)}
        </ProjectActionButton>
      ))}
    </Space> })
  return columns
}
