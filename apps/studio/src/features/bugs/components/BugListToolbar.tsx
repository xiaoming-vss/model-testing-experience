import { DownloadOutlined, FilterOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { Button, Checkbox, Input, Popover, Select, Space, Tooltip } from 'antd'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { listItems } from '@/services/api'
import { BUG_STATUS_LABELS, BUG_SEVERITY_LABELS, BUG_RESOLUTION_LABELS } from '../utils/bugMeta'
import type { useBugList } from '../hooks/useBugList'
type Model = ReturnType<typeof useBugList>
export function BugListToolbar({ model }: { model: Model }) {
  const { activeProjectId, activeSprintId, sprints, sprintsQuery, selectSprint, sprintSelectorOptions,
    keyword, setKeyword, bugsQuery, setCreateOpen, setImportOpen } = model
  return (
          <div className="panel-header api-panel-header bugs-toolbar tp-list-toolbar">
            <div className="api-filter-group bugs-filters">
              <h1 className="tp-list-title">Bug 列表</h1>
              <div className="api-filter-field">
                <span className="api-filter-field-label">迭代</span>
                <Select
                  className="api-filter-select business-filter-select"
                  value={activeSprintId ?? 'all'}
                  options={sprintSelectorOptions}
                  loading={sprintsQuery.isLoading}
                  placeholder="全部迭代"
                  onChange={(value: string) => selectSprint(value === 'all' ? 'all' : value)}
                />
              </div>
              <div className="api-filter-field bugs-search-field">
                <Input
                  className="api-filter-input bugs-search-input"
                  allowClear
                  prefix={<SearchOutlined />}
                  placeholder="搜索 Bug ID / 标题"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>
            </div>

            <Space size={8} className="bugs-toolbar-actions">
              <Popover trigger="click" placement="bottomRight" title="筛选与显示" content={<BugListFilters model={model} />}>
                <Button type="text" icon={<FilterOutlined />} aria-label="筛选与显示">
                  筛选{(model.status || model.confirmed !== undefined || model.resolution || model.severity || model.assigneeUserId) ? ' · 已启用' : ''}
                </Button>
              </Popover>
              <Tooltip title="刷新 Bug 列表">
                <ProjectActionButton
                  action="bug_read"
                  type="text"
                  shape="circle"
                  className="action-btn-read bugs-refresh"
                  operation="refresh"
                  icon={<ReloadOutlined />}
                  iconOnly
                  aria-label="刷新 Bug 列表"
                  loading={bugsQuery.isFetching}
                  onClick={() => bugsQuery.refetch()}
                />
              </Tooltip>
              <ProjectActionButton
                action="write"
                className="action-btn-read"
                icon={<DownloadOutlined />}
                disabled={!activeProjectId}
                onClick={() => setImportOpen(true)}
              >
                从禅道导入
              </ProjectActionButton>
              <ProjectActionButton
                action="write"
                type="primary"
                className="action-btn-create"
                operation="create"
                disabled={!activeProjectId || sprints.length === 0}
                onClick={() => setCreateOpen(true)}
              >
                新建 Bug
              </ProjectActionButton>
            </Space>
          </div>
  )
}
function BugListFilters({ model }: { model: Model }) {
  const { status, setStatus, confirmed, setConfirmed, resolution, setResolution, severity, setSeverity,
    assigneeUserId, setAssigneeUserId, membersQuery, optionalColumns, setOptionalColumns } = model
  return (
              <div className="bugs-filter-popover">
              <div className="api-filter-field">
                <span className="bug-filter-label">状态</span>
                <Select
                  className="api-filter-select business-filter-select"
                  allowClear
                  value={status || undefined}
                  options={Object.entries(BUG_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
                  placeholder="全部状态"
                  onChange={(value) => setStatus(value ?? '')}
                />
              </div>
              <div className="api-filter-field">
                <span className="bug-filter-label">确认情况</span>
                <Select allowClear aria-label="确认情况" value={confirmed === undefined ? undefined : Number(confirmed)}
                  options={[{ value: 0, label: '未确认' }, { value: 1, label: '已确认' }]} placeholder="全部"
                  onChange={(value) => setConfirmed(value === undefined ? undefined : value === 1)} />
              </div>
              <div className="api-filter-field">
                <span className="bug-filter-label">解决方案</span>
                <Select allowClear aria-label="解决方案筛选" value={resolution || undefined}
                  options={Object.entries(BUG_RESOLUTION_LABELS).map(([value, label]) => ({ value, label }))}
                  placeholder="全部" onChange={(value) => setResolution(value ?? '')} />
              </div>
              <div className="api-filter-field">
                <span className="bug-filter-label">严重程度</span>
                <Select
                  className="api-filter-select business-filter-select"
                  allowClear
                  value={severity || undefined}
                  options={Object.entries(BUG_SEVERITY_LABELS).map(([value, label]) => ({ value, label }))}
                  placeholder="全部"
                  onChange={(value) => setSeverity(value ?? '')}
                />
              </div>
              <div className="api-filter-field">
                <span className="bug-filter-label">责任人</span>
                <Select
                  className="api-filter-select business-filter-select"
                  showSearch
                  allowClear
                  optionFilterProp="label"
                  value={assigneeUserId || undefined}
                  options={listItems(membersQuery.data).map((member) => ({
                    label: member.name || member.userId,
                    value: member.userId,
                  }))}
                  placeholder="全部"
                  onChange={(value) => setAssigneeUserId(value ?? '')}
                />
              </div>
                <span className="bug-filter-label">附加显示列</span>
                <Checkbox.Group
                  value={optionalColumns} onChange={setOptionalColumns} className="bug-column-options"
                  options={[{ label: '所属需求', value: 'requirement' }, { label: '创建时间', value: 'createdAt' },
                    { label: '关联测试单', value: 'order' }, { label: '关联用例', value: 'case' }]} />
                <Button onClick={model.resetFilters}>清空筛选</Button>
              </div>

  )
}
