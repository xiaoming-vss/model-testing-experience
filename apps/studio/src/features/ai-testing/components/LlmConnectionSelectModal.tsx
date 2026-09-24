import '@/features/ai-testing/styles/index.css'
import '@/features/ai-testing/styles/task-form.css'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { LinkOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Modal, Radio, Space, Spin, Switch, Tag, Typography, theme } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, listItems } from '@/services/api'
import { getErrorMessage } from '@/utils/format'

const { Text } = Typography

export function LlmConnectionSelectModal({
  open,
  onClose,
  onConfirm,
  projectId,
  loading,
  showCheckpointOption = false,
  checkpointEnabled = false,
  onCheckpointEnabledChange,
}: {
  open: boolean
  onClose: () => void
  onConfirm: (connectionId: string) => void
  projectId?: string
  loading?: boolean
  showCheckpointOption?: boolean
  checkpointEnabled?: boolean
  onCheckpointEnabledChange?: (enabled: boolean) => void
}) {
  const { token } = theme.useToken()
  const navigate = useNavigate()
  const [selectedId, setSelectedId] = useState<string>('')

  const connectionsQuery = useQuery({
    queryKey: ['llmConnections', projectId, 'select'],
    queryFn: () => api.getLlmConnections(projectId!),
    enabled: open && Boolean(projectId),
  })

  const activeConnections = useMemo(
    () => listItems(connectionsQuery.data).filter((conn) => conn.status === 'active'),
    [connectionsQuery.data],
  )

  function handleConfirm() {
    if (!activeConnections.some(c => c.connectionId === selectedId)) return
    onConfirm(selectedId)
  }

  function handleClose() {
    setSelectedId('')
    onCheckpointEnabledChange?.(false)
    onClose()
  }

  function handleGoToConfig() {
    handleClose()
    navigate('/base-services?tab=llm')
  }

  return (
    <Modal
      mask={{ closable: false }}
      rootClassName="llm-connection-select-modal"
      // 模型选择可能由层级为 PopupBase + 200 的优化弹窗触发。
      zIndex={token.zIndexPopupBase + 300}
      title="选择本人 LLM 授权"
      open={open}
      onCancel={handleClose}
      width={480}
      destroyOnHidden
      afterClose={() => setSelectedId('')}
      footer={
        <Space>
          <Button onClick={handleClose}>取消</Button>
          <ProjectActionButton action="execute"
            type="primary"
            disabled={!activeConnections.some(c => c.connectionId === selectedId)}
            loading={loading}
            onClick={handleConfirm}
          >
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Text type="secondary">请选择本人的 LLM 连接用于本次操作：</Text>
          <Radio.Group
            value={selectedId}
            onChange={(e) => setSelectedId(e.target.value)}
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
          {showCheckpointOption ? (
            <div
              style={{
                padding: '12px 14px',
                border: '1px solid var(--tp-border-soft, rgba(148, 163, 184, 0.18))',
                borderRadius: 10,
                background: 'var(--tp-surface-soft, rgba(148, 163, 184, 0.06))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 16,
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <Text strong>开启阶段卡点审核</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  开启后每个生成阶段会暂停，可编辑确认后再继续。
                </Text>
              </div>
              <Switch checked={checkpointEnabled} onChange={onCheckpointEnabledChange} />
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  )
}
