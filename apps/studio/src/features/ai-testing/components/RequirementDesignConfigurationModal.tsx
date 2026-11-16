import { Alert, Form, Modal } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { aiTestingApi } from '../api/aiTesting.api'
import {
  requirementDesignApi,
  type RequirementDesignKind,
  type RequirementDesignTask,
} from '../api/requirementDesign.api'
import { getErrorMessage } from '@/utils/format'
import { randomId } from '@/shared/utils/crypto'
import { ApiInterfaceSelector, type ApiSuggestedRepository } from './ApiInterfaceSelector'

const getters = {
  requirement_analysis: aiTestingApi.getRequirementAnalysisTask,
  function: aiTestingApi.getFunctionalCaseGenerateTask,
  api: aiTestingApi.getApiCaseGenerateTask,
  ui: aiTestingApi.getUiCaseGenerateTask,
}

export function RequirementDesignConfigurationModal({
  requirementId,
  projectId,
  kind,
  tasks,
  initialTaskId,
  readOnly = false,
  suggestedRepositories,
  onClose,
  onSaved,
}: {
  requirementId: string
  projectId: string
  kind: RequirementDesignKind
  tasks: RequirementDesignTask[]
  initialTaskId?: string
  readOnly?: boolean
  suggestedRepositories?: ApiSuggestedRepository[]
  onClose: () => void
  onSaved: (taskId: string) => void
}) {
  const [requestId] = useState(() => randomId())
  const [taskId] = useState(initialTaskId || tasks[0]?.taskId || 'new')
  const [createdTaskId, setCreatedTaskId] = useState<string>()
  const [interfaceIds, setInterfaceIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const loadedTaskId = useRef<string | undefined>(undefined)
  const query = useQuery({
    queryKey: ['requirementDesignConfiguration', kind, taskId],
    queryFn: () => getters[kind](taskId),
    enabled: taskId !== 'new',
  })
  useEffect(() => {
    if (query.data && loadedTaskId.current !== taskId) {
      loadedTaskId.current = taskId
      if ('interfaceIds' in query.data && Array.isArray(query.data.interfaceIds)) {
        setInterfaceIds(query.data.interfaceIds)
      } else {
        setInterfaceIds([])
      }
    }
  }, [query.data, taskId])
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
          query.isFetching ||
          Boolean(query.error) ||
          (kind === 'api' && !interfaceIds.length),
      }}
    >
      <Form layout="vertical">
        {error || query.error ? (
          <Alert showIcon type="error" title={getErrorMessage(error ?? query.error)} />
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
            description="请在需求生成全景的 UI 测试分组中选择画像版本、前端仓库和 commit 模式。"
          />
        ) : null}
      </Form>
    </Modal>
  )
}
