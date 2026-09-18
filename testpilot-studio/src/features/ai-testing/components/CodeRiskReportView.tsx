import { Alert, Card, Descriptions, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMemo } from 'react'
import type { CodeRiskReport, CodeRiskReportRepository } from '@/features/ai-testing/types'
import { formatTime } from '@/utils/format'

const { Text, Title, Paragraph } = Typography

function getRiskLevelMeta(level?: string) {
  const normalized = (level ?? '').toLowerCase()
  if (normalized === 'high') return { label: '高', color: 'red' }
  if (normalized === 'medium' || normalized === 'middle') return { label: '中', color: 'orange' }
  if (normalized === 'low') return { label: '低', color: 'blue' }
  return { label: level || '未知', color: 'default' }
}

function getCaseTypeLabel(caseType?: string) {
  if (caseType === 'api') return 'API'
  if (caseType === 'ui') return 'UI'
  if (caseType === 'functional' || caseType === 'function') return '功能'
  return caseType || '-'
}

function getOverviewBlocks(changeOverview?: CodeRiskReport['changeOverview']) {
  if (!changeOverview) return []
  const blocks = [
    { key: 'filesChanged', label: '变更文件数', value: changeOverview.filesChanged },
    { key: 'additions', label: '新增行数', value: changeOverview.additions },
    { key: 'deletions', label: '删除行数', value: changeOverview.deletions },
  ]
  return blocks.filter((block) => typeof block.value === 'number')
}

export function CodeRiskReportView({ report }: { report: CodeRiskReport }) {
  const repositoryRows = useMemo(
    () =>
      (report.repositories ?? []).map((repository) => ({
        key: [repository.repositoryId, repository.branch].filter(Boolean).join('|'),
        ...repository,
      })),
    [report.repositories],
  )
  const repositoryColumns: TableProps<CodeRiskReportRepository & { key: string }>['columns'] = [
    { title: '仓库', dataIndex: 'repositoryId', key: 'repositoryId', ellipsis: true },
    { title: '分支', dataIndex: 'branch', key: 'branch', width: 160 },
    { title: '变更文件数', dataIndex: 'filesChanged', key: 'filesChanged', width: 96, align: 'right' },
    { title: '新增行', dataIndex: 'additions', key: 'additions', width: 96, align: 'right' },
    { title: '删除行', dataIndex: 'deletions', key: 'deletions', width: 96, align: 'right' },
    {
      title: '基线 → Head SHA',
      key: 'commits',
      render: (_, repository) => (
        <Text type="secondary" className="code-risk-report-sha" ellipsis>
          {repository.baselineCommit || 'none'} → {repository.headCommit || '-'}
        </Text>
      ),
    },
  ]

  const overviewBlocks = getOverviewBlocks(report.changeOverview)
  const risks = report.risks ?? []
  const affectedCases = report.affectedCases ?? []
  const coverageGaps = report.coverageGaps ?? []

  return (
    <div className="code-risk-report">
      <Card className="ai-task-detail-card code-risk-report-header" size="small">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="分析时间">{formatTime(report.analyzedAt ?? undefined)}</Descriptions.Item>
          <Descriptions.Item label="仓库">
            {repositoryRows.length === 0 ? (
              <Text type="secondary">-</Text>
            ) : (
              <ul className="code-risk-report-repositories">
                {repositoryRows.map((repository) => (
                  <li key={repository.key}>
                    {repository.repositoryId || '-'}（{repository.branch || '-'}）· 基线 {repository.baselineCommit || 'none'} → head{' '}
                    {repository.headCommit || '-'}
                  </li>
                ))}
              </ul>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="变更概览">
        {overviewBlocks.length === 0 && repositoryRows.length === 0 ? (
          <Empty description="暂无变更概览" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <>
            {overviewBlocks.length > 0 ? (
              <Space size={16} wrap className="code-risk-report-overview-summary">
                {overviewBlocks.map((block) => (
                  <span key={block.key} className="code-risk-report-overview-metric">
                    <span className="code-risk-report-overview-value">{block.value}</span>
                    <span className="code-risk-report-overview-label">{block.label}</span>
                  </span>
                ))}
              </Space>
            ) : null}
            {repositoryRows.length > 0 ? (
              <Table<CodeRiskReportRepository & { key: string }>
                className="code-risk-report-table"
                columns={repositoryColumns}
                dataSource={repositoryRows}
                pagination={false}
                size="small"
              />
            ) : null}
          </>
        )}
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="风险点清单">
        {risks.length === 0 ? (
          <Empty description="暂无风险点" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <ul className="code-risk-report-risks">
            {risks.map((risk, index) => {
              const levelMeta = getRiskLevelMeta(risk.level)
              return (
                <li key={index} className="code-risk-report-risk">
                  <Tag color={levelMeta.color}>{levelMeta.label}</Tag>
                  <span className="code-risk-report-risk-location">{risk.location || '-'}</span>
                  <Text type="secondary" className="code-risk-report-risk-reason">
                    {risk.reason || '-'}
                  </Text>
                </li>
              )
            })}
          </ul>
        )}
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="受影响已有用例">
        {affectedCases.length === 0 ? (
          <Empty description="暂不受影响的已有用例" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <ul className="code-risk-report-cases">
            {affectedCases.map((item, index) => (
              <li key={index} className="code-risk-report-case">
                <Tag color="geekblue">{getCaseTypeLabel(item.caseType)}</Tag>
                <span className="code-risk-report-case-title">{item.title || item.caseId || '-'}</span>
                {item.suiteName ? <Tag>{item.suiteName}</Tag> : null}
                <Text type="secondary" className="code-risk-report-case-impact">
                  {item.impact || '-'}
                </Text>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="覆盖缺口与建议">
        {coverageGaps.length === 0 ? (
          <Empty description="暂无覆盖缺口" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <ul className="code-risk-report-gaps">
            {coverageGaps.map((gap, index) => (
              <li key={index} className="code-risk-report-gap">
                <Title level={5} className="code-risk-report-gap-title">
                  {gap.gap || '-'}
                </Title>
                <Paragraph className="code-risk-report-gap-suggestion">
                  <Text type="secondary">建议：</Text>
                  {gap.suggestion || '-'}
                </Paragraph>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {!report.analyzedAt &&
      repositoryRows.length === 0 &&
      overviewBlocks.length === 0 &&
      risks.length === 0 &&
      affectedCases.length === 0 &&
      coverageGaps.length === 0 ? (
        <Alert showIcon type="warning" title="报告中暂无有效区块，可查看运行历史中的 resultYaml 原文" />
      ) : null}
    </div>
  )
}
