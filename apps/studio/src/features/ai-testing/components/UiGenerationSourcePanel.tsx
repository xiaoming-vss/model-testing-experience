import { Alert, Button, Progress, Upload } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { ActionButton } from '@/shared/components/ActionButton'
import { getErrorMessage } from '@/utils/format'
import { aiTestingApi } from '../api/aiTesting.api'
import { requirementDesignApi } from '../api/requirementDesign.api'

/** 维护任务当前源码包；历史产物的输入快照继续只读。 */
export function UiGenerationSourcePanel({ requirementId, taskId, canWrite, busy, onSaved }: {
  requirementId: string; taskId?: string; canWrite: boolean; busy: boolean; onSaved: () => void
}) {
  const client = useQueryClient()
  const createdTaskId = useRef<string | undefined>(undefined)
  const submitting = useRef(false)
  const [requestId] = useState(() => crypto.randomUUID())
  const [file, setFile] = useState<File>()
  const [saving, setSaving] = useState(false)
  const [savedName, setSavedName] = useState('')
  const [progress, setProgress] = useState<number>()
  const [error, setError] = useState<unknown>()
  const task = useQuery({ queryKey: ['uiGenerationInputTask', taskId],
    queryFn: () => aiTestingApi.getUiCaseGenerateTask(taskId!), enabled: Boolean(taskId), retry: false })
  const disabled = busy || saving || task.isFetching || Boolean(task.error)
  async function save() {
    if (!canWrite || disabled || !file || submitting.current) return
    submitting.current = true
    setSaving(true); setError(undefined); setSavedName('')
    try {
      let id = taskId ?? createdTaskId.current
      if (!id) {
        const configured = await requirementDesignApi.configure(requirementId, 'ui', { requestId, newConfiguration: false })
        id = configured.taskId
        if (!id) throw new Error('未能创建 UI 测试设置，请重试')
        createdTaskId.current = id
      }
      setProgress(0)
      const updated = await aiTestingApi.uploadUiCaseGenerateTaskSourceArchive(id, file, setProgress)
      client.setQueryData(['uiGenerationInputTask', id], updated)
      setSavedName(updated.sourceArchive?.filename ?? file.name)
      setFile(undefined); setProgress(100)
      onSaved()
    } catch (reason) { setError(reason) }
    finally { setSaving(false); submitting.current = false }
  }
  return <section className="gc-inspector-section gc-inspector-source" aria-label="UI 测试源码包">
    <h3>源码包</h3>
    <p>{file?.name ?? (savedName || task.data?.sourceArchive?.filename || (task.isFetching ? '正在读取源码包' : '尚未上传源码包'))}</p>
    {canWrite ? <>
      <Upload accept=".zip" maxCount={1} disabled={disabled}
        fileList={file ? [{ uid: file.name, name: file.name, status: 'done' }] : []}
        beforeUpload={selected => {
          if (!selected.name.toLowerCase().endsWith('.zip')) { setError(new Error('请选择 ZIP 源码包')); return Upload.LIST_IGNORE }
          setFile(selected); setError(undefined); setSavedName(''); setProgress(undefined); return false
        }} onRemove={() => { setFile(undefined); setProgress(undefined); return true }}>
        <ActionButton operation="upload" size="small" disabled={disabled}>{task.data?.sourceArchive ? '替换源码包' : '添加源码包'}</ActionButton>
      </Upload>
      {file ? <Button type="primary" size="small" loading={saving} disabled={disabled} onClick={() => void save()}>保存源码包</Button> : null}
    </> : null}
    {progress !== undefined ? <Progress percent={progress} status={error ? 'exception' : undefined} /> : null}
    {savedName ? <span role="status">源码包已保存</span> : null}
    {error || task.error ? <Alert showIcon type="error" title={getErrorMessage(error ?? task.error)}
      action={task.error ? <Button size="small" onClick={() => void task.refetch()}>重试读取</Button> : undefined} /> : null}
    <p className="gc-inspector-summary">源码包用于下一轮生成，历史版本保留原有输入快照。</p>
  </section>
}
