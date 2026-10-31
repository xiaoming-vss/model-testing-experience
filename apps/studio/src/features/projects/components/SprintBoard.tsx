import { useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Alert, Button, Empty, Popconfirm, Skeleton } from 'antd'
import { AppIcon } from '@/shared/icons'
import { ListPagination } from '@/shared/components/ListPagination'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { formatTime, getErrorMessage, normalizeSprintId, pickEndTime, pickStartTime } from '@/utils/format'
import type { Sprint } from '../types'
import { ProjectActionButton } from './ProjectActionButton'
import { isInteractiveCardTarget } from '../utils/cardNavigation'
import '../styles/sprint-board.css'

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
  const current = Math.min(page, Math.max(1, Math.ceil(ordered.length / pageSize)))
  const visible = ordered.slice((current - 1) * pageSize, current * pageSize)
  return <div className="sprint-board tp-list-body">
    <div className="sprint-board-scroll" aria-busy={loading}>
      {error ? <Alert type="error" showIcon title={getErrorMessage(error)} action={<Button loading={refreshing} onClick={onRefresh}>重试读取</Button>} /> : null}
      {loading ? <Skeleton active title paragraph={{ rows: 4 }} /> : null}
      {!loading && !error && !ordered.length ? <Empty description="暂无迭代，创建后即可开始管理需求与测试" /> : null}
      {!loading ? <div className="sprint-board-grid" aria-label="迭代列表">{visible.map(sprint => {
        const group = groups.find(item => item.key === groupKey(sprint.status))!
        const sprintId = normalizeSprintId(sprint)
        return <article key={sprintId} className={`sprint-board-card sprint-board-card-${group.key}`}
          onClick={(event) => {
            if (isInteractiveCardTarget(event.target)) return
            if (sprintId && projectId) navigate(`/projects/${projectId}/sprints/${sprintId}`)
          }}>
            <div className="sprint-board-main">
              <div className="sprint-board-title-row">
                <h3 className="sprint-board-title"><Link to={`/projects/${projectId}/sprints/${sprintId}`} title={sprint.name}>{sprint.name}</Link></h3>
                <span className={`sprint-board-status sprint-board-status-${group.key}`}>
                  {group.key === 'other' ? sprint.status || '未知状态' : group.label}
                </span>
              </div>
              <div className="sprint-board-doc">
                <span className="sprint-board-doc-icon" aria-hidden="true"><AppIcon name="sprint" size={13} /></span>
                <span className="sprint-board-doc-text" title={sprint.description || '暂无迭代描述'}>{sprint.description || '暂无迭代描述'}</span>
              </div>
              <dl className="sprint-board-meta">
                <div><dt>开始时间</dt><dd><time>{displayTime(pickStartTime(sprint))}</time></dd></div>
                <div><dt>结束时间</dt><dd><time>{displayTime(pickEndTime(sprint))}</time></dd></div>
              </dl>
            </div>
            <footer className="sprint-board-foot">
              <div className="sprint-board-binding">{renderBinding(sprint)}</div>
              <div className="sprint-board-actions">
                <ProjectActionButton action="write" operation="edit" iconOnly onClick={() => onEdit(sprint)}>编辑</ProjectActionButton>
                <ProjectActionButton action="manage" operation="bind" iconOnly onClick={() => onBind(sprint)}>禅道绑定</ProjectActionButton>
                <Popconfirm title="确认删除该迭代？" okText="删除" cancelText="取消" onConfirm={() => onDelete(normalizeSprintId(sprint))}>
                  <ProjectActionButton action="write" operation="delete" iconOnly loading={deletingId === normalizeSprintId(sprint)}>删除</ProjectActionButton>
                </Popconfirm>
              </div>
            </footer>
          </article>
      })}</div> : null}
    </div>
    <div className="table-footer"><ListPagination current={page} pageSize={pageSize} total={ordered.length}
      loading={refreshing || Boolean(error)} onChange={(next, size) => { setPage(size === pageSize ? next : 1); setPageSize(size) }} /></div>
  </div>
}
