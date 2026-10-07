import type { ReactNode } from 'react'
import { Typography } from 'antd'
import { Link } from 'react-router-dom'
import { pickCreatedAt, formatTime, pickUpdatedAt } from '@/utils/format'
import type { Bug } from '../types'
import { BUG_PRIORITY_LABELS, BUG_SEVERITY_LABELS, getBugPriorityTone, BUG_RESOLUTION_LABELS } from '../utils/bugMeta'
const { Text } = Typography

export function BugDetailSidebar({ bug, projectName, sprintNames, resolveUserName, children, editors, canReadContext = true }: {
  canReadContext?: boolean
  editors?: { severity: ReactNode; priority: ReactNode; plannedFixSprint: ReactNode; requirement: ReactNode }
  children?: ReactNode
  bug: Bug; projectName?: string; sprintNames: Map<string, string>; resolveUserName: (id: string) => string
}) {
  return (
          <div className="bug-detail-side">
            <section className="bug-detail-panel">
              <h2 className="bug-panel-title">基本属性</h2>
              <dl className="bug-meta-list">
                <dt>所属项目</dt>
                <dd>{projectName ?? bug.projectId}</dd>
                <dt>严重程度</dt>
                <dd>{editors?.severity ?? <span className={`bug-sidebar-indicator ${bug.severity === 'critical' || bug.severity === 'serious' ? 'tone-red' : 'tone-amber'}`}>{BUG_SEVERITY_LABELS[bug.severity] ?? bug.severity}</span>}</dd>
                <dt>优先级</dt>
                <dd>{editors?.priority ?? <span className={`bug-sidebar-indicator tone-${getBugPriorityTone(bug.priority)}`}>{BUG_PRIORITY_LABELS[bug.priority] ?? bug.priority}</span>}</dd>
                <dt>确认情况</dt>
                <dd>{bug.confirmed ? '已确认' : '未确认'}</dd>
                {bug.resolution && <><dt>解决方案</dt><dd>{BUG_RESOLUTION_LABELS[bug.resolution] ?? bug.resolution}</dd></>}
                {bug.resolution === 'fixed' && <><dt>解决版本</dt><dd>{bug.resolvedBuild || '历史记录未提供'}</dd></>}
                {bug.resolution === 'duplicate' && <><dt>重复 Bug ID</dt><dd>{bug.duplicateBug}</dd></>}
                <dt>创建人</dt>
                <dd>{resolveUserName(bug.reporterUserId)}</dd>
                <dt>责任人</dt>
                <dd className="bug-sidebar-person"><span className="bug-person-avatar" aria-hidden="true">{resolveUserName(bug.assigneeUserId).slice(0, 1).toUpperCase()}</span>{resolveUserName(bug.assigneeUserId)}</dd>
                <dt>发现迭代</dt>
                <dd>{sprintNames.get(bug.foundSprintId) ?? '-'}</dd>
                <dt>计划修复迭代</dt>
                <dd>
                  {editors?.plannedFixSprint ?? (bug.plannedFixSprintId ? sprintNames.get(bug.plannedFixSprintId) ?? '-' : '未安排')}
                </dd>
                <dt>创建时间</dt>
                <dd>{formatTime(pickCreatedAt(bug))}</dd>
                <dt>更新时间</dt>
                <dd>{formatTime(pickUpdatedAt(bug))}</dd>
              </dl>
            </section>

            <section className="bug-detail-panel">
              <h2 className="bug-panel-title">关联上下文与追溯</h2>
              <dl className="bug-meta-list bug-context-list">
                <dt>所属需求</dt>
                <dd>
                  {editors?.requirement ?? (bug.requirementId && canReadContext ? (
                    <Link className="bug-link-text" to={`/requirements/${bug.requirementId}`}>{bug.requirementName || bug.requirementId}</Link>
                  ) : (
                    <Text type="secondary">{bug.requirementName || (bug.requirementId ? '已关联需求' : '未关联需求')}</Text>
                  ))}
                </dd>
                <dt>关联测试单</dt>
                <dd>
                  {bug.sourceOrderId && canReadContext ? (
                    <Link className="bug-link-text" to={`/test-orders/${bug.sourceOrderId}`}>
                      {bug.sourceOrderName || bug.sourceOrderId}
                    </Link>
                  ) : (
                    <Text type="secondary">{bug.sourceOrderName || (bug.sourceOrderId ? '已关联测试单' : '未关联测试单')}</Text>
                  )}
                </dd>
                <dt>关联用例</dt>
                <dd>{bug.sourceOrderId && bug.sourceEntryId && canReadContext ? (
                  <Link to={`/test-orders/${bug.sourceOrderId}?entryId=${bug.sourceEntryId}`}>
                    {bug.sourceCaseTitle || '查看用例'}
                  </Link>
                ) : <Text type="secondary">{bug.sourceCaseTitle || '未关联用例'}</Text>}</dd>
                <dt>执行记录</dt>
                <dd>
                  {bug.sourceEntryId && canReadContext ? (
                    <Link to={`/test-orders/${bug.sourceOrderId}?entryId=${bug.sourceEntryId}`}>查看执行记录</Link>
                  ) : (
                    <Text type="secondary">{bug.sourceEntryId ? '已关联执行记录' : '未关联执行记录'}</Text>
                  )}
                </dd>
              </dl>
            </section>
            {children}
          </div>
  )
}
