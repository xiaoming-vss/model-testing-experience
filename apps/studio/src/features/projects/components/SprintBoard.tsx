import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Empty, Popconfirm, Skeleton } from 'antd'
import { AppIcon } from '@/shared/icons'
import { ListPagination } from '@/shared/components/ListPagination'
import { EntityCard } from '@/shared/components/EntityCard'
import { ListSurface } from '@/shared/components/ListSurface'
import { DEFAULT_PAGE_SIZE, pageSlice } from '@/shared/utils/pagination'
import { entityCardGridClass } from '@/shared/utils/surfaceClasses'
import { formatTime, getErrorMessage, normalizeSprintId, pickEndTime, pickStartTime } from '@/utils/format'
import type { Sprint } from '@/domain/projects/types'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'

const groups = [
  { key: 'running', label: '进行中' },
  { key: 'planned', label: '未开始' },
  { key: 'completed', label: '已完成' },
  { key: 'other', label: '其他状态' },
]
const groupKey = (status: string) => groups.some(group => group.key === status) ? status : 'other'
const displayTime = (value?: string) => formatTime(value).replace(/:\d{2}$/, '')

export function SprintBoard({ projectId, sprints, loading, refreshing, error, deletingId,
  onRefresh, onEdit, onDelete, onBind, renderBinding }: {
  projectId?: string; sprints: Sprint[]; loading: boolean; refreshing: boolean; error: unknown; deletingId?: string
  onRefresh: () => void; onEdit: (sprint: Sprint) => void
  onDelete: (id: string) => void; onBind: (sprint: Sprint) => void; renderBinding: (sprint: Sprint) => ReactNode
}) {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const ordered = groups.flatMap(group => sprints.filter(sprint => groupKey(sprint.status) === group.key))
  const visible = pageSlice(ordered, page, pageSize)
  return <ListSurface className="sprint-board-shell tp-surface" bodyClassName="sprint-board text-[var(--srf-text)]"
    scrollClassName="sprint-board-scroll" scrollAriaBusy={loading}
    footer={<ListPagination current={page} pageSize={pageSize} total={ordered.length}
      loading={refreshing || Boolean(error)} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size) }} />}>
    {error ? <Alert type="error" showIcon title={getErrorMessage(error)} action={<Button loading={refreshing} onClick={onRefresh}>重试读取</Button>} /> : null}
    {loading ? <Skeleton active title paragraph={{ rows: 4 }} /> : null}
    {!loading && !error && !ordered.length ? <Empty description="暂无迭代，创建后即可开始管理需求与测试" /> : null}
    {!loading ? <div className={`entity-card-grid sprint-board-grid ${entityCardGridClass}`} aria-label="迭代列表">{visible.map(sprint => {
      const group = groups.find(item => item.key === groupKey(sprint.status))!
      const sprintId = normalizeSprintId(sprint)
      return <EntityCard key={sprintId} className={`sprint-board-card sprint-board-card-${group.key} max-[680.01px]:[&_.entity-card-foot]:flex-wrap`}
        titleAs="h3" titleId={`sprint-title-${sprintId}`}
        title={<Link to={`/projects/${projectId}/sprints/${sprintId}`} title={sprint.name}>{sprint.name}</Link>}
        status={<span className={`sprint-board-status sprint-board-status-${group.key} inline-flex flex-none items-center gap-[5px] whitespace-nowrap text-[10.5px] font-medium leading-[18px] ${group.key === 'running' ? 'text-[var(--app-action-read)]' : group.key === 'completed' ? 'text-[var(--app-result-success-text)]' : 'text-[var(--srf-text-muted)]'}`}>
          {group.key === 'other' ? sprint.status || '未知状态' : group.label}
        </span>}
        meta={[
          { label: '开始时间', value: <time>{displayTime(pickStartTime(sprint))}</time> },
          { label: '结束时间', value: <time>{displayTime(pickEndTime(sprint))}</time> },
        ]}
        footerNote={renderBinding(sprint)} footerNoteClassName="sprint-board-binding flex min-w-0 flex-[1_1_auto] items-center whitespace-normal text-[10.5px] leading-[18px] text-[var(--srf-text-secondary)] max-[680.01px]:flex-[1_1_100%]"
        actions={<>
          <ProjectActionButton action="write" operation="edit" iconOnly onClick={() => onEdit(sprint)}>编辑</ProjectActionButton>
          <ProjectActionButton action="manage" operation="bind" iconOnly onClick={() => onBind(sprint)}>禅道绑定</ProjectActionButton>
          <Popconfirm title="确认删除该迭代？" okText="删除" cancelText="取消" onConfirm={() => onDelete(normalizeSprintId(sprint))}>
            <ProjectActionButton action="write" operation="delete" iconOnly loading={deletingId === normalizeSprintId(sprint)}>删除</ProjectActionButton>
          </Popconfirm>
        </>}
        actionsClassName="sprint-board-actions flex flex-none items-center justify-end text-[var(--app-action-read)] max-[680.01px]:ml-auto"
        onOpen={() => { if (sprintId && projectId) navigate(`/projects/${projectId}/sprints/${sprintId}`) }}>
        <div className="sprint-board-doc m-0 mb-2.5 flex min-w-0 items-start gap-2 text-[10.5px] leading-4 text-[var(--srf-text-secondary)]">
          <span className="sprint-board-doc-icon inline-flex h-[22px] w-[22px] flex-none items-center justify-center rounded-[6px] bg-[var(--app-accent-surface)] text-[var(--app-action-read)] [&_svg]:h-[13px] [&_svg]:w-[13px]" aria-hidden="true"><AppIcon name="sprint" size={13} /></span>
          <span className="sprint-board-doc-text line-clamp-2 max-h-8 min-w-0 overflow-hidden [overflow-wrap:anywhere]" title={sprint.description || '暂无迭代描述'}>{sprint.description || '暂无迭代描述'}</span>
        </div>
      </EntityCard>
    })}</div> : null}
  </ListSurface>
}
