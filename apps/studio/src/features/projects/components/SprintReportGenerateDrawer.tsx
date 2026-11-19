import { Alert, Button, Drawer, Empty, Form, Input, Select, Space, Spin } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FormInstance } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { api, listItems } from '@/services/api'
import { getErrorMessage } from '@/utils/format'
import type { TestReportGenerateFormValues } from '../utils/sprintReport'
import sprintOverviewStyles from '../styles/sprint-overview.module.css'

export function TestReportGenerateDrawer({
  open,
  projectId,
  form,
  snapshotDate,
  loading,
  error,
  onClose,
  onFinish,
}: {
  open: boolean
  projectId?: string
  form: FormInstance<TestReportGenerateFormValues>
  snapshotDate: string
  loading?: boolean
  error?: unknown
  onClose: () => void
  onFinish: (values: TestReportGenerateFormValues) => void
}) {
  const navigate = useNavigate()
  const connectionsQuery = useQuery({
    queryKey: ['llmConnections', projectId, 'testReportGenerate'],
    queryFn: () => api.getLlmConnections(projectId!),
    enabled: open && Boolean(projectId),
  })
  const activeConnections = useMemo(
    () => listItems(connectionsQuery.data).filter((connection) => connection.status === 'active'),
    [connectionsQuery.data],
  )

  function handleGoToConfig() {
    onClose()
    navigate('/base-services?tab=llm')
  }

  return (
    <Drawer
      title="生成测试报告"
      open={open}
      onClose={onClose}
      width={520}
      destroyOnHidden
      rootClassName={sprintOverviewStyles.root}
      extra={
        <Space>
          <Button onClick={onClose}>取消</Button>
          <ProjectActionButton action="execute" type="primary" loading={loading} disabled={activeConnections.length === 0} onClick={() => form.submit()}>
            确认生成
          </ProjectActionButton>
        </Space>
      }
    >
      {connectionsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} style={{ marginBottom: 16 }} /> : null}
      {!projectId ? <Alert showIcon type="info" title="缺少项目信息，无法加载 LLM 连接" style={{ marginBottom: 16 }} /> : null}
      {error ? <Alert showIcon type="error" title={getErrorMessage(error)} style={{ marginBottom: 16 }} /> : null}
      <Form form={form} layout="vertical" requiredMark={false} onFinish={onFinish}>
        <Form.Item label="快照日期">
          <Input value={snapshotDate} readOnly />
        </Form.Item>
        <Form.Item name="connectionId" label="LLM 连接" rules={[{ required: true, message: '请选择 LLM 连接' }]}>
          <Select
            loading={connectionsQuery.isLoading}
            placeholder="请选择用于生成报告的 LLM 连接"
            options={activeConnections.map((connection) => ({
              value: connection.connectionId,
              label: connection.modelId ? `${connection.name} (${connection.modelId})` : connection.name,
            }))}
            notFoundContent={
              connectionsQuery.isLoading ? <Spin size="small" /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用的 LLM 连接" />
            }
          />
        </Form.Item>
        {activeConnections.length === 0 && !connectionsQuery.isLoading && !connectionsQuery.error ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可用的 LLM 连接" className="sprint-report-drawer-empty m-0 mb-4">
            <Button type="primary" onClick={handleGoToConfig}>
              去配置
            </Button>
          </Empty>
        ) : null}
        <Form.Item name="instruction" label="生成说明">
          <Input.TextArea maxLength={1000} rows={5} placeholder="可选，补充本次报告生成要求" showCount />
        </Form.Item>
      </Form>
    </Drawer>
  )
}
