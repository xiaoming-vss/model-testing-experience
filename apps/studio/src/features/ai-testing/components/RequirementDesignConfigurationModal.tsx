import { Alert, Form, Modal } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { requirementDesignApi, type RequirementDesignKind } from '../api/requirementDesign.api'
import { getErrorMessage } from '@/utils/format'
import { randomId } from '@/shared/utils/crypto'
import { ApiInterfaceSelector, type ApiSuggestedRepository } from './ApiInterfaceSelector'

export function RequirementDesignConfigurationModal({
  requirementId,
  projectId,
  kind,
  initialTaskId,
  readOnly = false,
  suggestedRepositories,
  onClose,
  onSaved,
}: {
  requirementId: string
  projectId: string
  kind: RequirementDesignKind
  initialTaskId?: string
  readOnly?: boolean
  suggestedRepositories?: ApiSuggestedRepository[]
  onClose: () => void
  onSaved: (taskId: string) => void
}) {
  const [requestId] = useState(() => randomId())
  const [taskId] = useState(initialTaskId || 'new')
  const [createdTaskId, setCreatedTaskId] = useState<string>()
  const [interfaceIds, setInterfaceIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const loadedInterfaceIds = useRef(false)
  const overview = useQuery({
    queryKey: ['requirementDesignOverview', requirementId],
    queryFn: () => requirementDesignApi.overview(requirementId),
    enabled: kind === 'api',
  })
  useEffect(() => {
    if (kind !== 'api' || loadedInterfaceIds.current || !overview.data) return
    loadedInterfaceIds.current = true
    const task = overview.data.tasks.find(item => item.kind === 'api' && item.taskId === taskId)
      ?? overview.data.tasks.find(item => item.kind === 'api')
    setInterfaceIds(task?.interfaceIds ?? [])
  }, [kind, overview.data, taskId])
  async function save() {
    setSaving(true)
    setError(undefined)
    try {
      if (kind === 'api' && !interfaceIds.length) {
        throw new Error('请至少选择一个接口')
      }
      const configured = await requirementDesignApi.configure(requirementId, kind, {
        requestId,
        taskId: createdTaskId ?? (taskId === 'new' ? undefined : taskId),
        newConfiguration: false,
        ...(kind === 'api' ? { interfaceIds } : {}),
      })
      const id = configured.taskId!
      setCreatedTaskId(id)
      onSaved(id)
    } catch (reason) {
      setError(reason)
    } finally {
      setSaving(false)
    }
  }
  return (
    <Modal
      open
      centered
      title="生成设置"
      onCancel={() => {
        if (!saving) onClose()
      }}
      onOk={() => void save()}
      okText="保存设置"
      cancelText="取消"
      confirmLoading={saving}
      footer={readOnly ? null : undefined}
      mask={{ closable: false }}
      width={kind === 'api' ? 'min(960px, calc(100vw - 32px))' : 680}
      okButtonProps={{
        disabled:
          overview.isFetching ||
          Boolean(overview.error) ||
          (kind === 'api' && !interfaceIds.length),
      }}
    >
      <Form layout="vertical">
        {error || overview.error ? (
          <Alert showIcon type="error" title={getErrorMessage(error ?? overview.error)} />
        ) : null}
        {kind === 'api' ? (
          <Form.Item
            label="生成接口"
            extra={
              suggestedRepositories?.length
                ? '接口来自接口库；默认展示仓库画像建议的后端仓库，可切换范围选择其他软件仓库的接口。'
                : '接口来自接口库；运行时读取最新定义。默认展示需求关联软件仓库下的接口。'
            }
          >
            <ApiInterfaceSelector
              projectId={projectId}
              requirementId={requirementId}
              value={interfaceIds}
              onChange={setInterfaceIds}
              disabled={readOnly || saving}
              suggestedRepositories={suggestedRepositories}
            />
          </Form.Item>
        ) : null}
        {kind === 'ui' ? (
          <Alert
            showIcon
            type="info"
            title="UI 生成来源由仓库画像提供"
            description="请在需求生成全景的 UI 测试分组中查看当前画像并选择前端仓库和 commit 模式。"
          />
        ) : null}
      </Form>
    </Modal>
  )
}
