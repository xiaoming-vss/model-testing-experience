import { Alert, Button, Modal, Progress, Upload } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { getErrorMessage } from '@/utils/format'
import { aiTestingApi } from '../api/aiTesting.api'
import type { UiGenerationSourceInputs } from '../api/generationChain.api'
import { UiGenerationCaseSelector } from './UiGenerationCaseSelector'
import '../styles/ui-generation-inputs.css'

export function UiGenerationInputsModal({ requirementId, projectId, taskId, refreshInputs, source, onClose, onSubmit }: {
  requirementId: string
  projectId: string
  taskId: string
  refreshInputs: boolean
  source?: UiGenerationSourceInputs | null
  onClose: () => void
  onSubmit: (inputs: { refreshInputs: boolean; functionCaseIds: string[] }) => Promise<unknown>
}) {
  const client = useQueryClient()
  const access = useProjectAccess(projectId)
  const [ids, setIds] = useState<string[] | undefined>(() => source?.cases.length ? source.cases.map(item => item.caseId) : undefined)
  const [ready, setReady] = useState(false)
  const [file, setFile] = useState<File>()
  const [progress, setProgress] = useState<number>()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<unknown>()
  const submitting = useRef(false)
  const queryKey = ['uiGenerationInputTask', taskId]
  const task = useQuery({ queryKey, queryFn: () => aiTestingApi.getUiCaseGenerateTask(taskId), retry: false })
  async function submit() {
    if (submitting.current || !ready || !ids?.length) return
    submitting.current = true
    setSaving(true); setError(undefined)
    try {
      if (file) {
        setProgress(0)
        const updated = await aiTestingApi.uploadUiCaseGenerateTaskSourceArchive(taskId, file, setProgress)
        client.setQueryData(queryKey, updated)
        setFile(undefined)
        setProgress(100)
      }
      await onSubmit({ refreshInputs, functionCaseIds: ids })
      onClose()
    } catch (reason) { setError(reason) }
    finally { setSaving(false); submitting.current = false }
  }
  return <Modal open centered destroyOnHidden title={refreshInputs ? '更换输入并重新生成' : '选择 UI 生成输入'}
    width={880} className="gc-ui-input-modal" mask={{ closable: false }}
    onCancel={() => { if (!saving) onClose() }} onOk={() => void submit()}
    cancelText="取消" okText={refreshInputs ? '从元素控件清单重新生成' : '开始生成'} confirmLoading={saving}
    okButtonProps={{ disabled: saving || !ready || task.isFetching || Boolean(task.error) || (!file && !task.data?.sourceArchive?.fileId) }}>
    {refreshInputs ? <Alert showIcon type="info" title="将从元素控件清单开始新一轮生成"
      description="旧版本及其输入快照保留；UI 用例设计与 YAML 需要使用新一轮的上游产物重新生成。" /> : null}
    {task.error || error ? <Alert showIcon type="error" title={getErrorMessage(error ?? task.error)}
      action={task.error ? <Button onClick={() => void task.refetch()}>重新读取</Button> : undefined} /> : null}
    <section className="gc-ui-source-upload" aria-label="生成源码包">
      <h3>源码 ZIP</h3>
      <p>{file?.name ?? task.data?.sourceArchive?.filename ?? (task.isFetching ? '正在读取源码包' : '尚未上传源码包')}</p>
      {access.can('write') ? <Upload accept=".zip" maxCount={1} disabled={saving || task.isFetching}
        fileList={file ? [{ uid: file.name, name: file.name, status: 'done' }] : []}
        beforeUpload={selected => { setFile(selected); return false }}
        onRemove={() => { setFile(undefined); return true }}>
        <Button disabled={saving || task.isFetching}>上传 / 替换源码包</Button>
      </Upload> : null}
      {progress !== undefined ? <Progress percent={progress} status={error ? 'exception' : undefined} /> : null}
    </section>
    {!task.isFetching && !task.error && !file && !task.data?.sourceArchive?.fileId ? <Alert showIcon type="info" title="请先上传有效的源码 ZIP，再开始生成" /> : null}
    <fieldset disabled={saving} className="gc-ui-input-cases">
      <UiGenerationCaseSelector requirementId={requirementId} open value={ids} onChange={setIds} onReady={setReady} />
    </fieldset>
  </Modal>
}
