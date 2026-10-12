import { ActionButton } from '@/shared/components/ActionButton'
import { Alert, Form, Input, Modal, Progress, Upload } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { aiTestingApi } from '../api/aiTesting.api'
import { requirementDesignApi, type RequirementDesignKind, type RequirementDesignTask } from '../api/requirementDesign.api'
import { getErrorMessage } from '@/utils/format'

const getters = {
  requirement_analysis: aiTestingApi.getRequirementAnalysisTask,
  function: aiTestingApi.getFunctionalCaseGenerateTask,
  api: aiTestingApi.getApiCaseGenerateTask,
  ui: aiTestingApi.getUiCaseGenerateTask,
}

export function RequirementDesignConfigurationModal({ requirementId, kind, tasks, initialTaskId, onClose, onSaved }: {
  requirementId: string
  kind: RequirementDesignKind
  tasks: RequirementDesignTask[]
  initialTaskId?: string
  onClose: () => void
  onSaved: (taskId: string) => void
}) {
  const [requestId] = useState(() => crypto.randomUUID())
  const [taskId] = useState(initialTaskId ?? tasks[0]?.taskId ?? 'new')
  const [createdTaskId, setCreatedTaskId] = useState<string>()
  const [source, setSource] = useState('')
  const [archive, setArchive] = useState<File>()
  const [uploadProgress, setUploadProgress] = useState<number>()
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
      if (kind === 'ui') {
        if (archive) { setUploadProgress(0); await aiTestingApi.uploadUiCaseGenerateTaskSourceArchive(id, archive, setUploadProgress); setUploadProgress(100) }
        else if (!tasks.find(task => task.taskId === id)?.hasSource) throw new Error('设置已保存，请上传源码 ZIP 后继续')
      }
      onSaved(id)
    } catch (reason) { setError(reason) }
    finally { setSaving(false) }
  }
  return <Modal open centered title="生成设置" onCancel={() => { if (!saving) onClose() }} onOk={() => void save()}
    okText="保存设置" cancelText="取消" confirmLoading={saving} mask={{ closable: false }} width={680}
    okButtonProps={{ disabled: query.isFetching || Boolean(query.error) }}>
    <Form layout="vertical">
      {error || query.error ? <Alert showIcon type="error" title={getErrorMessage(error ?? query.error)} /> : null}
      {kind === 'api' ? <Form.Item label="OpenAPI / Swagger 文档">
        <Upload disabled={saving} accept=".json,.yaml,.yml" showUploadList={false} beforeUpload={file => { void file.text().then(setSource).catch(setError); return false }}>
          <ActionButton operation="upload" size="small">载入文档</ActionButton>
        </Upload>
        <Input.TextArea disabled={saving} aria-label="OpenAPI / Swagger 文档" value={source} onChange={event => setSource(event.target.value)} autoSize={{ minRows: 8, maxRows: 16 }} placeholder="粘贴 OpenAPI / Swagger JSON 或 YAML" />
      </Form.Item> : null}
      {kind === 'ui' ? <Form.Item label="源码 ZIP">
        <p>{archive?.name ?? tasks.find(task => task.taskId === taskId)?.sourceFilename ?? '尚未上传源码包'}</p>
        <Upload disabled={saving} accept=".zip" maxCount={1} fileList={archive ? [{ uid: archive.name, name: archive.name, status: 'done' }] : []}
          beforeUpload={file => { setArchive(file); return false }} onRemove={() => { setArchive(undefined); return true }}>
          <ActionButton operation="upload" size="small" disabled={saving}>上传 / 替换源码包</ActionButton>
        </Upload>
      </Form.Item> : null}
      {uploadProgress !== undefined ? <Progress percent={uploadProgress} status={error ? 'exception' : undefined} /> : null}
    </Form>
  </Modal>
}
