import { Space, Tooltip, Typography } from 'antd'
import type { TableProps } from 'antd'
import { Link } from 'react-router-dom'
import { AppIcon } from '@/shared/icons'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { pickCreatedAt, formatTime, pickUpdatedAt } from '@/utils/format'
import type { Bug, BugAction, BugSortField } from '../types'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS, BUG_ACTION_ICONS, getBugStateLabel, getBugActions,
  getBugPriorityTone, getBugStatusTone, getBugActionLabel } from '../utils/bugMeta'
const { Text } = Typography

export type BugSortState = { by: BugSortField; order: 'asc' | 'desc' }

/** 列 key → 后端排序字段；业务档位（状态/严重程度/优先级）按档位升序即严重在前。 */
const SORT_FIELD_BY_KEY: Record<string, BugSortField> = {
  id: 'id', status: 'status', severity: 'severity', priority: 'priority',
  createdAt: 'created_at', updatedAt: 'updated_at',
}

export function bugColumns({ memberNameMap, sprintNameMap, onTransition, onEdit, optionalColumns, sort }: {
  optionalColumns: string[]
  memberNameMap: Map<string, string>; sprintNameMap: Map<string, string>
  onTransition: (bug: Bug, action: BugAction) => void
  onEdit: (bug: Bug) => void
  sort: BugSortState
}): NonNullable<TableProps<Bug>['columns']> {
  // 服务端分页排序：sorter 只负责发起请求，列头箭头由 sort 受控。
  const sorter = (key: string, directions: NonNullable<TableProps<Bug>['columns']>[number]['sortDirections']) => {
    const field = SORT_FIELD_BY_KEY[key]
    if (!field) return {}
    return {
      sorter: true,
      sortDirections: directions,
      sortOrder: sort.by === field
        ? sort.order === 'asc' ? 'ascend' as const : 'descend' as const
        : null,
    }
  }
  const columns: NonNullable<TableProps<Bug>['columns']> = [
    { title: 'Bug 标题', key: 'title',
      render: (_, bug) => <Space size={8} className="tp-list-name functional-suite-list-name bug-title-cell">
        <span className="bug-name-icon"><AppIcon name="navBug" size={16} /></span>
        <span className="bug-list-number">#{bug.id}</span>
        {/* Link 自己完成跳转并阻止冒泡，否则行 onRow 会再推一次相同路由，返回时要多点一次。 */}
        <Tooltip title={bug.title}><Link className="ant-typography bug-title-text" to={`/bugs/${bug.bugId}`}
          onClick={(event) => event.stopPropagation()}>{bug.title}</Link></Tooltip>
      </Space> },
    { title: '状态', key: 'status', width: 150, align: 'center', ...sorter('status', ['ascend', 'descend']),
      render: (_, bug) => <span className={`bug-status-pill tone-${getBugStatusTone(bug.status)}`}>
        <span className="bug-status-dot" />{getBugStateLabel(bug)}</span> },
    { title: '严重程度', key: 'severity', width: 110, align: 'center', ...sorter('severity', ['ascend', 'descend']),
      render: (_, bug) => <Text className="bug-muted-cell">{BUG_SEVERITY_LABELS[bug.severity] ?? bug.severity}</Text> },
    { title: '优先级', key: 'priority', width: 80, align: 'center', ...sorter('priority', ['ascend', 'descend']),
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
    { title: '创建时间', key: 'createdAt', width: 160, ...sorter('createdAt', ['descend', 'ascend']),
      render: (_, bug) => <Text className="bug-time-cell" type="secondary" title={formatTime(pickCreatedAt(bug))}>{formatTime(pickCreatedAt(bug)).replace(/:\d{2}$/, '')}</Text> },
  ]
  const optional: NonNullable<TableProps<Bug>['columns']> = [
    { key: 'requirement', title: '所属需求', width: 180, ellipsis: true,
      render: (_, bug) => bug.requirementName || '未关联需求' },
    { key: 'updatedAt', title: '更新时间', width: 160, ...sorter('updatedAt', ['descend', 'ascend']),
      render: (_, bug) => <Text className="bug-time-cell" type="secondary">{formatTime(pickUpdatedAt(bug))}</Text> },
    { key: 'order', title: '关联测试单', width: 180, ellipsis: true,
      render: (_, bug) => bug.sourceOrderName || '未关联测试单' },
    { key: 'case', title: '关联用例', width: 180, ellipsis: true,
      render: (_, bug) => bug.sourceCaseTitle || '未关联用例' },
  ]
  columns.push(...optional.filter((column) => optionalColumns.includes(String(column.key))))
  columns.push({ title: <span className="tp-actions-col-title" style={{ width: 92 }}>操作</span>, key: 'actions', width: 128, align: 'right', fixed: 'right',
    render: (_, bug) => <Space size={4} className="bug-row-actions" onClick={(event) => event.stopPropagation()}>
      {(getBugActions(bug)).map((action) => {
        const ActionIcon = BUG_ACTION_ICONS[action]
        return (
          <Tooltip key={action} title={getBugActionLabel(action)}>
            <ProjectActionButton action="bug_handle" type="text" size="small" shape="circle"
              className={`app-action app-action-icon${action === 'activate' ? ' app-action-delete' : ''}`}
              danger={action === 'activate'}
              icon={<ActionIcon />} aria-label={getBugActionLabel(action)}
              onClick={() => onTransition(bug, action)} />
          </Tooltip>
        )
      })}
      <ProjectActionButton action="write" type="text" size="small" shape="circle"
        operation="edit" iconOnly aria-label="编辑"
        onClick={() => onEdit(bug)} />
    </Space> })
  return columns
}
