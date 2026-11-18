import { Alert, Card, Empty, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import type { RepositoryProfile, RepositoryProfileRepository } from '../types'
import { formatProfileConfidence, repositoryRoleMeta } from '../utils/repositoryProfileDisplay'

const { Text, Paragraph } = Typography

export function RepositoryProfileReportView({
  profile,
  profileErrors = {},
}: {
  profile: RepositoryProfile
  profileErrors?: Record<string, string>
}) {
  const repositories = profile.repositories ?? []
  const columns: TableProps<RepositoryProfileRepository>['columns'] = [
    {
      title: '仓库',
      dataIndex: 'pathWithNamespace',
      key: 'pathWithNamespace',
      ellipsis: true,
      render: (_, repository) => (
        <Text strong ellipsis={{ tooltip: repository.pathWithNamespace }}>
          {repository.pathWithNamespace || repository.repositoryId}
        </Text>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 112,
      render: (_, repository) => {
        const meta = repositoryRoleMeta(repository.role)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '职责',
      dataIndex: 'responsibilitySummary',
      key: 'responsibilitySummary',
      ellipsis: true,
      render: (_, repository) => (
        <Text ellipsis={{ tooltip: repository.responsibilitySummary }}>
          {repository.responsibilitySummary}
        </Text>
      ),
    },
  ]

  if (!repositories.length) {
    return (
      <Card className="ai-task-detail-card repository-profile-report" size="small">
        <Empty description="暂无仓库画像" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }

  return (
    <div className="repository-profile-report flex flex-col gap-3">
      <Card className="ai-task-detail-card repository-profile-summary" size="small" title="整体画像">
        <Paragraph className="repository-profile-summary-text m-0">{profile.overallSummary}</Paragraph>
      </Card>
      <Card className="ai-task-detail-card repository-profile-table-card" size="small" title="仓库角色">
        <Table<RepositoryProfileRepository>
          className="repository-profile-table"
          size="small"
          columns={columns}
          dataSource={repositories}
          rowKey={repository => repository.repositoryId}
          pagination={false}
          expandable={{
            expandedRowRender: repository => (
              <div className="repository-profile-details flex flex-col gap-3 px-0.5 py-1">
                {profileErrors[repository.repositoryId] ? (
                  <Alert
                    showIcon
                    type="warning"
                    title="仓库读取失败"
                    description={profileErrors[repository.repositoryId]}
                  />
                ) : null}
                <DescriptionsGrid repository={repository} />
              </div>
            ),
            rowExpandable: () => true,
          }}
        />
      </Card>
    </div>
  )
}

function DescriptionsGrid({ repository }: { repository: RepositoryProfileRepository }) {
  return (
    <dl className="repository-profile-detail-grid m-0 grid grid-cols-2 gap-x-6 gap-y-3 max-[900.01px]:grid-cols-1">
      <div>
        <dt className="text-[12px] leading-[22px] text-[var(--app-surface-text-muted)]">仓库 ID</dt>
        <dd className="m-0 min-w-0 leading-[22px] [overflow-wrap:anywhere]">
          <Text code>{repository.repositoryId}</Text>
        </dd>
      </div>
      <div>
        <dt className="text-[12px] leading-[22px] text-[var(--app-surface-text-muted)]">置信度</dt>
        <dd className="m-0 min-w-0 leading-[22px] [overflow-wrap:anywhere]">{formatProfileConfidence(repository.confidence)}</dd>
      </div>
      <div>
        <dt className="text-[12px] leading-[22px] text-[var(--app-surface-text-muted)]">技术栈</dt>
        <dd className="m-0 min-w-0 leading-[22px] [overflow-wrap:anywhere]">
          {repository.techStack.length ? (
            <Space size={4} wrap>
              {repository.techStack.map(item => (
                <Tag key={item}>{item}</Tag>
              ))}
            </Space>
          ) : (
            <Text type="secondary">未识别</Text>
          )}
        </dd>
      </div>
      <div>
        <dt className="text-[12px] leading-[22px] text-[var(--app-surface-text-muted)]">关键目录</dt>
        <dd className="m-0 min-w-0 leading-[22px] [overflow-wrap:anywhere]">
          {repository.keyPaths.length ? (
            <Space size={4} wrap>
              {repository.keyPaths.map(item => (
                <Text key={item} code>
                  {item}
                </Text>
              ))}
            </Space>
          ) : (
            <Text type="secondary">未识别</Text>
          )}
        </dd>
      </div>
      <div>
        <dt className="text-[12px] leading-[22px] text-[var(--app-surface-text-muted)]">证据</dt>
        <dd className="m-0 min-w-0 leading-[22px] [overflow-wrap:anywhere]">
          {repository.evidence.length ? (
            <ul className="repository-profile-evidence m-0 pl-[18px]">
              {repository.evidence.map(item => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <Text type="secondary">无</Text>
          )}
        </dd>
      </div>
    </dl>
  )
}
