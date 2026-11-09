import { Alert, Card, Descriptions, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useMemo } from 'react'
import type {
  CodeRiskContextReceipt,
  CodeRiskContextReceiptRepository,
  CodeRiskReport,
  CodeRiskReportRepository,
} from '@/features/ai-testing/types'
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

  if (report.contextReceipt) {
    return <CodeRiskContextReceiptView report={report} receipt={report.contextReceipt} />
  }

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

function CodeRiskContextReceiptView({
  report,
  receipt,
}: {
  report: CodeRiskReport
  receipt: CodeRiskContextReceipt
}) {
  const repositories = receipt.repositories ?? []
  const counts = receipt.counts ?? {}
  const columns: TableProps<CodeRiskContextReceiptRepository & { key: string }>['columns'] = [
    { title: '仓库', dataIndex: 'repositoryId', key: 'repositoryId', ellipsis: true },
    { title: '路径', dataIndex: 'pathWithNamespace', key: 'pathWithNamespace', ellipsis: true },
    { title: '分支', dataIndex: 'branch', key: 'branch', width: 160 },
    {
      title: '基线 → HEAD',
      key: 'commits',
      render: (_, repository) => (
        <Text type="secondary" className="code-risk-report-sha" ellipsis>
          {repository.baseCommit || 'none'} → {repository.headCommit || '-'}
        </Text>
      ),
    },
    { title: '变更文件', dataIndex: 'filesChanged', key: 'filesChanged', width: 96, align: 'right' },
  ]
  const rows = repositories.map((repository, index) => ({
    key: [repository.instanceUrl, repository.repositoryId, repository.headCommit]
      .filter(Boolean)
      .join('|') || String(index),
    ...repository,
  }))

  return (
    <div className="code-risk-report">
      <Alert
        showIcon
        type="info"
        title="上下文预览（分析 skill 未启用）"
        description="本次运行只验证代码拉取、上下文组装和模型读取，不产出正式风险结论。"
      />
      <Card className="ai-task-detail-card code-risk-report-header" size="small" title="上下文回执">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="分析时间">
            {formatTime(report.analyzedAt ?? undefined)}
          </Descriptions.Item>
          <Descriptions.Item label="仓库数">{counts.repositories ?? repositories.length}</Descriptions.Item>
          <Descriptions.Item label="变更文件数">{counts.changedFiles ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="Diff 字符数">{counts.diffChars ?? '-'}</Descriptions.Item>
          <Descriptions.Item label="模型摘要">{receipt.summary || '-'}</Descriptions.Item>
          <Descriptions.Item label="使用工具">
            {(receipt.toolsUsed ?? []).length === 0 ? (
              <Text type="secondary">未记录</Text>
            ) : (
              <Space size={4} wrap>
                {(receipt.toolsUsed ?? []).map((tool, index) => (
                  <Tag key={`${tool}-${index}`}>{tool}</Tag>
                ))}
              </Space>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="仓库与代码版本">
        {rows.length === 0 ? (
          <Empty description="暂无仓库回执" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table<CodeRiskContextReceiptRepository & { key: string }>
            className="code-risk-report-table"
            columns={columns}
            dataSource={rows}
            pagination={false}
            size="small"
          />
        )}
      </Card>

      <Card className="ai-task-detail-card code-risk-report-block" size="small" title="模型读取的文件">
        {(receipt.filesRead ?? []).length === 0 ? (
          <Text type="secondary">模型未列出读取文件</Text>
        ) : (
          <ul className="code-risk-report-cases">
            {(receipt.filesRead ?? []).map((file, index) => (
              <li key={`${file}-${index}`} className="code-risk-report-case">
                <Text className="code-risk-report-case-title">{file}</Text>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {(receipt.truncatedFiles ?? []).length > 0 ? (
        <Alert
          showIcon
          type="warning"
          title="部分 diff 因上下文预算被排除"
          description={(receipt.truncatedFiles ?? []).join('、')}
        />
      ) : null}
    </div>
  )
}
