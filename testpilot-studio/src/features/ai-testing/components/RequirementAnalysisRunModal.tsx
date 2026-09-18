import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Form, Input, Modal, Radio, Space, Spin, Switch, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, listItems } from '@/services/api'
import { getErrorMessage } from '@/utils/format'

const { Text } = Typography

export type RequirementAnalysisRunFormValues = {
  connectionId: string
  instruction?: string
  checkpointEnabled?: boolean
}

export function RequirementAnalysisRunModal({
  open,
  onClose,
  onConfirm,
  projectId,
  loading,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (values: RequirementAnalysisRunFormValues) => void
  projectId?: string
  loading?: boolean
}) {
  const navigate = useNavigate()
  const [form] = Form.useForm<RequirementAnalysisRunFormValues>()
  const [selectedId, setSelectedId] = useState('')

  const connectionsQuery = useQuery({
    queryKey: ['llmConnections', projectId, 'requirementAnalysisRun'],
    queryFn: () => api.getLlmConnections(projectId!),
    enabled: open && Boolean(projectId),
  })

  const activeConnections = useMemo(
    () => listItems(connectionsQuery.data).filter((conn) => conn.status === 'active'),
    [connectionsQuery.data],
  )

  function resetAndClose() {
    setSelectedId('')
    form.resetFields()
    onClose()
  }

  function handleGoToConfig() {
    resetAndClose()
    navigate('/base-services?tab=llm')
  }

  return (
    <Modal
      mask={{ closable: false }}
      title="运行需求分析"
      open={open}
      onCancel={resetAndClose}
      width={520}
      destroyOnHidden
      afterClose={() => {
        setSelectedId('')
        form.resetFields()
      }}
      footer={
        <Space>
          <Button onClick={resetAndClose}>取消</Button>
          <ProjectActionButton action="execute" type="primary" disabled={!selectedId} loading={loading} onClick={() => form.submit()}>
            确认运行
          </ProjectActionButton>
        </Space>
      }
    >
      {connectionsQuery.isLoading ? (
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin />
        </div>
      ) : connectionsQuery.error ? (
        <Alert showIcon type="error" title={getErrorMessage(connectionsQuery.error)} />
      ) : !projectId ? (
        <Alert showIcon type="info" title="请先选择项目" />
      ) : activeConnections.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <Text>暂无可用的 LLM 连接</Text>
              <Text type="secondary">请先前往基础设施页面配置 LLM 连接。</Text>
            </div>
          }
        >
          <Button type="primary" icon={<LinkOutlined />} onClick={handleGoToConfig}>
            去配置
          </Button>
        </Empty>
      ) : (
        <Form<RequirementAnalysisRunFormValues>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) =>
            onConfirm({
              connectionId: values.connectionId,
              instruction: values.instruction?.trim() ?? '',
              checkpointEnabled: Boolean(values.checkpointEnabled),
            })
          }
        >
          <Form.Item name="connectionId" label="LLM 连接" rules={[{ required: true, message: '请选择 LLM 连接' }]}>
            <Radio.Group
              value={selectedId}
              onChange={(event) => {
                setSelectedId(event.target.value)
                form.setFieldValue('connectionId', event.target.value)
              }}
              style={{ width: '100%' }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {activeConnections.map((conn) => (
                  <Radio
                    key={conn.connectionId}
                    value={conn.connectionId}
                    style={{
                      padding: '12px 16px',
                      border: '1px solid var(--tp-border-soft, rgba(148, 163, 184, 0.18))',
                      borderRadius: 8,
                      margin: 0,
                      width: '100%',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Text strong>{conn.name}</Text>
                      {conn.modelId ? <Tag>{conn.modelId}</Tag> : null}
                    </div>
                  </Radio>
                ))}
              </div>
            </Radio.Group>
          </Form.Item>

          <Form.Item name="instruction" label="补充指令">
            <Input.TextArea maxLength={1000} rows={5} placeholder="例如：重点分析异常场景和歧义点" />
          </Form.Item>

          <Form.Item
            name="checkpointEnabled"
            label="阶段卡点审核"
            valuePropName="checked"
            extra="开启后，第一阶段和第二阶段完成后会等待人工审核，通过后继续下一阶段。"
          >
            <Switch />
          </Form.Item>
        </Form>
      )}
    </Modal>
  )
}
