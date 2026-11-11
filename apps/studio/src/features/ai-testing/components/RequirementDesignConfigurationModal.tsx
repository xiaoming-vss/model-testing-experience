import { ActionButton } from '@/shared/components/ActionButton'
import { Alert, Button, Form, Modal, Space, Upload } from 'antd'
import { parseDocument } from 'yaml'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { aiTestingApi } from '../api/aiTesting.api'
import { requirementDesignApi, type RequirementDesignKind, type RequirementDesignTask } from '../api/requirementDesign.api'
import { getErrorMessage } from '@/utils/format'
import { randomId } from '@/shared/utils/crypto'

const getters = {
  requirement_analysis: aiTestingApi.getRequirementAnalysisTask,
  function: aiTestingApi.getFunctionalCaseGenerateTask,
  api: aiTestingApi.getApiCaseGenerateTask,
  ui: aiTestingApi.getUiCaseGenerateTask,
}

export function RequirementDesignConfigurationModal({ requirementId, kind, tasks, initialTaskId, readOnly = false, onClose, onSaved }: {
  requirementId: string
  kind: RequirementDesignKind
  tasks: RequirementDesignTask[]
  initialTaskId?: string
  readOnly?: boolean
  onClose: () => void
  onSaved: (taskId: string) => void
}) {
  const [requestId] = useState(() => randomId())
  const [taskId] = useState(initialTaskId || tasks[0]?.taskId || 'new')
  const [createdTaskId, setCreatedTaskId] = useState<string>()
  const [source, setSource] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const loadedTaskId = useRef<string | undefined>(undefined)
  const query = useQuery({ queryKey: ['requirementDesignConfiguration', kind, taskId],
    queryFn: () => getters[kind](taskId), enabled: taskId !== 'new' })
  useEffect(() => {
    if (query.data && loadedTaskId.current !== taskId) {
      loadedTaskId.current = taskId
      setSource('sourceContent' in query.data && typeof query.data.sourceContent === 'string' ? query.data.sourceContent : '')
    }
  }, [query.data, taskId])
  function formatSource() {
    if (!source.trim()) return
    try {
      if (/^\s*[[{]/.test(source)) setSource(JSON.stringify(JSON.parse(source), null, 2))
      else {
        const document = parseDocument(source)
        if (document.errors.length) throw document.errors[0]
        setSource(document.toString())
      }
      setError(undefined)
    } catch {
      setError(new Error('文档格式不正确，请检查 JSON 或 YAML 后重试'))
    }
  }
  async function save() {
    setSaving(true); setError(undefined)
    try {
      const configured = await requirementDesignApi.configure(requirementId, kind, {
        requestId,
        taskId: createdTaskId ?? (taskId === 'new' ? undefined : taskId),
        newConfiguration: false,
        ...(kind === 'api' ? { sourceContent: source } : {}),
      })
      const id = configured.taskId!
      setCreatedTaskId(id)
      onSaved(id)
    } catch (reason) { setError(reason) }
    finally { setSaving(false) }
  }
  return <Modal open centered title="生成设置" onCancel={() => { if (!saving) onClose() }} onOk={() => void save()}
    okText="保存设置" cancelText="取消" confirmLoading={saving} footer={readOnly ? null : undefined} mask={{ closable: false }} width={kind === 'api' ? 'min(960px, calc(100vw - 32px))' : 680}
    okButtonProps={{ disabled: query.isFetching || Boolean(query.error) }}>
    <Form layout="vertical">
      {error || query.error ? <Alert showIcon type="error" title={getErrorMessage(error ?? query.error)} /> : null}
      {kind === 'api' ? <Form.Item label="OpenAPI / Swagger 文档">
        <Space style={{ marginBottom: 8 }}>
          {!readOnly ? <Upload disabled={saving} accept=".json,.yaml,.yml" showUploadList={false} beforeUpload={file => { void file.text().then(setSource).catch(setError); return false }}>
            <ActionButton operation="upload" size="small">载入文档</ActionButton>
          </Upload> : null}
          {!readOnly ? <Button size="small" disabled={saving || !source.trim()} onClick={formatSource}>格式化</Button> : null}
        </Space>
        <TextCodeEditor readOnly={readOnly || saving} ariaLabel="OpenAPI / Swagger 文档" value={source} onChange={setSource}
          language="auto" height="min(45vh, 420px)" minHeight={240} />
      </Form.Item> : null}
      {kind === 'ui' ? <Alert showIcon type="info" title="UI 生成来源由仓库画像提供"
        description="请在需求生成全景的 UI 测试分组中选择画像版本、前端仓库和 commit 模式。" /> : null}
    </Form>
  </Modal>
}
