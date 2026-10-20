import { Typography } from 'antd'
import type { BugActivity } from '../types'
import { BUG_ACTIVITY_ACTION_LABELS, BUG_REJECT_REASON_LABELS, BUG_SEVERITY_LABELS, BUG_PRIORITY_LABELS, getBugStatusLabel, getBugStateLabel, BUG_RESOLUTION_LABELS } from '../utils/bugMeta'
import { RichTextViewer } from '@/shared/components/RichTextEditor'
import { UserDisplayName } from '@/shared/components/UserReference/UserReference'
import { pickCreatedAt, formatTime } from '@/utils/format'

const { Text } = Typography

function describeChange(change: { field: string; from: string; to: string }): string {
  const labels: Record<string, string> = {
    title: '标题',
    severity: '严重程度',
    priority: '优先级',
    plannedFixSprintId: '计划修复迭代',
    requirementId: '所属需求',
    descriptionHtml: '问题描述',
  }
  const values = change.field === 'severity' ? BUG_SEVERITY_LABELS : change.field === 'priority' ? BUG_PRIORITY_LABELS : {}
  return `${labels[change.field] ?? change.field}：${values[change.from] || change.from || '空'} → ${values[change.to] || change.to || '空'}`
}

/** 单条动态的描述文案；处理记录（status_change）会附带说明内容。 */
function activitySummary(activity: BugActivity, resolveUserName: (id: string) => string): string {
  if (activity.kind === 'transfer') {
    return `将责任人从 ${resolveUserName(activity.detail.fromUserId ?? '')} 转派给 ${resolveUserName(activity.detail.toUserId ?? '')}`
  }
  if (activity.kind === 'attachment') {
    const files = activity.detail.addedFiles ?? []
    const removed = activity.detail.removedFiles ?? []
    return [files.length ? `补充附件：${files.map((file) => file.filename).join('、')}` : '',
      removed.length ? `移除附件：${removed.map((file) => file.filename).join('、')}` : ''].filter(Boolean).join('；') || '更新了附件'
  }
  if (activity.kind === 'edit') {
    return '编辑了信息'
  }
  return BUG_ACTIVITY_ACTION_LABELS[activity.action] ?? activity.action
}

/** 通用动态列表：处理记录与评论动态共用，按时间正序展示。 */
export function BugActivityFeed({
  items,
  resolveUserName,
  emptyText = '暂无记录',
}: {
  items: BugActivity[]
  resolveUserName: (userId: string) => string
  emptyText?: string
}) {
  if (items.length === 0) {
    return (
      <Text type="secondary" className="bug-activity-empty">
        {emptyText}
      </Text>
    )
  }
  return (
    <ul className="bug-activity-list">
      {items.map((activity) => (
        <li key={activity.activityId} className="bug-activity-item">
          <div className="bug-activity-head">
            <span className="bug-activity-actor"><UserDisplayName name={resolveUserName(activity.actorUserId)} /></span>
            <span className="bug-activity-action">{activitySummary(activity, resolveUserName)}</span>
            {activity.kind === 'status_change' && activity.toStatus ? (
              <span className="bug-activity-status">{activity.fromStatus ? `${activity.detail.fromConfirmed === undefined ? getBugStatusLabel(activity.fromStatus) : getBugStateLabel({ status: activity.fromStatus, confirmed: activity.detail.fromConfirmed, resolution: activity.detail.fromResolution })} → ` : ''}{activity.detail.toConfirmed === undefined ? getBugStatusLabel(activity.toStatus) : getBugStateLabel({ status: activity.toStatus, confirmed: activity.detail.toConfirmed, resolution: activity.detail.toResolution })}</span>
            ) : null}
            <span className="bug-activity-time">{formatTime(pickCreatedAt(activity))}</span>
          </div>
          {activity.detail.rejectReason && <p className="bug-activity-content">拒绝原因：{BUG_REJECT_REASON_LABELS[activity.detail.rejectReason] ?? activity.detail.rejectReasonLabel}</p>}
          {activity.detail.toResolution && <p className="bug-activity-content">解决方案：{BUG_RESOLUTION_LABELS[activity.detail.toResolution] ?? activity.detail.toResolution}{activity.detail.resolvedBuild ? `；解决版本：${activity.detail.resolvedBuild}` : ''}{activity.detail.duplicateBug ? `；重复 Bug ID：${activity.detail.duplicateBug}` : ''}</p>}
          {activity.content ? (
            <p className="bug-activity-content">{activity.content}</p>
          ) : null}
          {activity.kind === 'edit' && (activity.detail.changes ?? []).length > 0 ? (
            <ul className="bug-activity-changes">
              {(activity.detail.changes ?? []).map((change) => (
                <li key={`${activity.activityId}-${change.field}`}>
                  {change.field === 'descriptionHtml' ? <details><summary>问题描述已修改 · 查看前后内容</summary>
                    <div className="bug-history-diff"><div><strong>修改前</strong><RichTextViewer html={change.from} /></div>
                      <div><strong>修改后</strong><RichTextViewer html={change.to} /></div></div>
                  </details> : describeChange(change)}
                </li>
              ))}
            </ul>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
