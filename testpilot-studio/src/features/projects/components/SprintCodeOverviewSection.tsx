import { ActionButton } from '@/shared/components/ActionButton'
import { usePersonalConnections } from '@/features/base-services/hooks/usePersonalConnections'
import { useState } from 'react'
import { PersonalConnectionFields } from '@/features/base-services/components/PersonalConnectionFields'

import { Alert, Card, Empty, Space, Tag, Tooltip, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { api, listItems, type SprintCodeOverviewRepository } from '@/services/api'
import { formatTime, getErrorMessage } from '@/utils/format'

const { Text, Title } = Typography

function formatBaseline(repository: SprintCodeOverviewRepository) {
  if (repository.error) return '-'
  if (repository.isNewRepository) return '新增仓库（无基线）'
  if (repository.baselineRef) return repository.baselineNote ? `${repository.baselineRef}（${repository.baselineNote}）` : repository.baselineRef
  return '-'
}

export function SprintCodeOverviewSection({ sprintId, projectId }: { sprintId: string; projectId: string }) {
  const [selectedConnections, setSelectedConnections] = useState<Record<string, string>>({})
  const personal = usePersonalConnections(projectId, 'gitlab', selectedConnections)
  const codeOverviewQuery = useQuery({
    queryKey: ['sprintCodeOverview', sprintId, selectedConnections],
    queryFn: () => api.getSprintCodeOverview(sprintId, selectedConnections),
    enabled: Boolean(sprintId),
  })
  const repositories = listItems(codeOverviewQuery.data?.repositories ?? [])

  return (
    <Card className="sprint-overview-card sprint-overview-card-rich sprint-code-overview-card">
      <div className="sprint-dashboard-card-head">
        <div>
          <Title level={4}>代码变更</Title>
          <Text type="secondary">
            {codeOverviewQuery.data?.generatedAt ? `统计时间：${formatTime(codeOverviewQuery.data.generatedAt)}` : '本迭代内需求绑定的仓库与代码变更量'}
          </Text>
        </div>
        <ActionButton
          className="action-btn-read"
          operation="refresh"
          loading={codeOverviewQuery.isFetching}
          onClick={() => codeOverviewQuery.refetch()}
        >
          手动刷新
        </ActionButton>
      </div>

      <PersonalConnectionFields instances={repositories.map(r => r.instanceUrl ?? '')} connections={personal.connections} value={selectedConnections} onChange={setSelectedConnections} />
      {codeOverviewQuery.error ? <Alert showIcon type="error" title={getErrorMessage(codeOverviewQuery.error)} /> : null}

      {codeOverviewQuery.isLoading ? (
        <Empty description="代码变更加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : !codeOverviewQuery.error && repositories.length === 0 ? (
        <Empty description="本迭代暂无需求代码绑定" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : repositories.length > 0 ? (
        <div className="sprint-code-overview-list">
          {repositories.map((repository) => (
            <div key={`${repository.instanceUrl}:${repository.repositoryId}:${repository.branch}`} className="sprint-code-overview-item">
              <div className="sprint-code-overview-item-head">
                <div className="sprint-code-overview-item-title">
                  <Tooltip title={repository.branch ? `${repository.name || repository.repositoryId} · ${repository.branch}` : repository.name || repository.repositoryId}>
                    <Text strong ellipsis>
                      {repository.name || repository.repositoryId}
                    </Text>
                  </Tooltip>
                  {repository.branch ? <Tag color="blue">{repository.branch}</Tag> : null}
                  {repository.isNewRepository ? <Tag color="gold">新增仓库</Tag> : null}
                </div>
                <Space size={8} className="sprint-code-overview-item-metrics">
                  <span className="sprint-code-overview-metric">
                    <span className="sprint-code-overview-metric-value">{repository.error ? '—' : repository.commitsCount}</span>
                    <span className="sprint-code-overview-metric-label">commits</span>
                  </span>
                  <span className="sprint-code-overview-metric metric-additions">
                    <span className="sprint-code-overview-metric-value">{repository.error ? '—' : `+${repository.additions}`} </span>
                    <span className="sprint-code-overview-metric-label">新增</span>
                  </span>
                  <span className="sprint-code-overview-metric metric-deletions">
                    <span className="sprint-code-overview-metric-value">{repository.error ? '—' : `-${repository.deletions}`} </span>
                    <span className="sprint-code-overview-metric-label">删除</span>
                  </span>
                </Space>
              </div>
              <div className="sprint-code-overview-item-meta">
                <Text type="secondary">{repository.instanceUrl} · 基线：{formatBaseline(repository)}</Text>
              </div>
              {repository.error ? (
                <Alert
                  showIcon
                  type="error"
                  className="sprint-code-overview-item-error"
                  title={repository.error}
                  description={repository.remediation || undefined}
                />
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
    </Card>
  )
}
