import { useRef, useState } from 'react'
import { Alert, Button, Input, Modal, Space } from 'antd'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/services/api'
import { getErrorMessage } from '@/utils/format'
import { randomId } from '@/shared/utils/crypto'
import { usePersonalLlmChoice } from '../hooks/usePersonalLlmChoice'
import type { ApiCaseGenerateTaskRun } from '../types'

export function ApiCheckpointActions({ run, projectId, canReview, canWrite, canExecute, onChange }: {
  run: ApiCaseGenerateTaskRun
  projectId?: string
  canReview: boolean
  canWrite: boolean
  canExecute: boolean
  onChange: (run: ApiCaseGenerateTaskRun) => void
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [savedDraft, setSavedDraft] = useState('')
  const [instruction, setInstruction] = useState('')
  const pendingRequest = useRef<{ key: string; id: string } | null>(null)
  const choice = usePersonalLlmChoice(projectId)
  const stage = run.currentStage === 'completed' ? 'generate' : run.currentStage
  const waiting = run.status === 'waiting_review' && stage === 'openapi_extract'
  const failed = ['failed', 'error'].includes(run.status ?? '') && (stage === 'openapi_extract' || stage === 'generate')
  const final = run.status === 'success' && stage === 'generate' && run.reviewStatus === 'pending'
  const mutation = useMutation({
    mutationFn: async (action: 'save' | 'approve' | 'reject' | 'retry' | 'revise') => {
      if (!run.runId || !stage) throw new Error('运行记录不可用')
      if (action === 'save') {
        let extraction: unknown
        try { extraction = JSON.parse(draft) } catch { throw new Error('接口配置必须是有效的 JSON') }
        return api.saveApiCaseStageOutput(run.runId, { apiExtraction: extraction })
      }
      if (action === 'approve' || action === 'reject') {
        const llmConnectionId = action === 'approve' ? await choice.choose() : undefined
        const key = JSON.stringify([run.runId, stage, action, llmConnectionId])
        if (pendingRequest.current?.key !== key) pendingRequest.current = { key, id: randomId() }
        return api.reviewApiCaseStage(run.runId, { stage, action, llmConnectionId, requestId: pendingRequest.current.id })
      }
      const llmConnectionId = await choice.choose()
      const key = JSON.stringify([run.runId, stage, action, llmConnectionId, instruction.trim()])
      if (pendingRequest.current?.key !== key) pendingRequest.current = { key, id: randomId() }
      if (action === 'retry') return api.retryApiCaseStage(run.runId, { stage, llmConnectionId, requestId: pendingRequest.current.id })
      if (!instruction.trim()) throw new Error('请填写优化要求')
      return api.reviseApiCaseStage(run.runId, { stage, revisionInstruction: instruction.trim(), llmConnectionId, requestId: pendingRequest.current.id })
    },
    onSuccess: (updated) => { pendingRequest.current = null; onChange(updated); setOpen(false); setInstruction('') },
  })
  if (!run.checkpointEnabled || !(waiting || failed || final)) return null
  function show() {
    const config = typeof run.configJson === 'string' ? (() => { try { return JSON.parse(run.configJson) } catch { return {} } })() : run.configJson
    const value = JSON.stringify((config as Record<string, unknown> | undefined)?.apiExtraction ?? {}, null, 2)
    setDraft(value)
    setSavedDraft(value)
    mutation.reset()
    setOpen(true)
  }
  return <>
    {choice.dialog}
    <Button size="small" onClick={(event) => { event.stopPropagation(); show() }}>{waiting ? '处理接口配置' : failed ? '重试阶段' : '优化候选'}</Button>
    <Modal open={open} title={waiting ? '接口配置检查点' : failed ? '重试生成阶段' : '优化候选结果'} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
      {mutation.error ? <Alert showIcon type="error" title={getErrorMessage(mutation.error)} /> : null}
      {waiting ? <><p>确认接口配置后继续生成 API 用例。</p><Input.TextArea aria-label="接口配置 JSON" value={draft} onChange={(event) => setDraft(event.target.value)} autoSize={{ minRows: 8, maxRows: 16 }} /></> : null}
      {(waiting || final) && canExecute ? <Input.TextArea aria-label="优化要求" placeholder="填写优化要求后选择优化" value={instruction} onChange={(event) => setInstruction(event.target.value)} autoSize={{ minRows: 2, maxRows: 4 }} /> : null}
      <Space wrap style={{ marginTop: 16 }}>
        <Button onClick={() => setOpen(false)}>关闭</Button>
        {waiting && canWrite ? <Button disabled={mutation.isPending} onClick={() => mutation.mutate('save')}>保存配置</Button> : null}
        {waiting && canReview ? <Button danger disabled={mutation.isPending || draft !== savedDraft} onClick={() => mutation.mutate('reject')}>拒绝</Button> : null}
        {waiting && canReview ? <Button type="primary" loading={mutation.isPending} disabled={draft !== savedDraft} onClick={() => mutation.mutate('approve')}>审核并继续</Button> : null}
        {failed && canExecute ? <Button type="primary" loading={mutation.isPending} onClick={() => mutation.mutate('retry')}>选择授权并重试</Button> : null}
        {(waiting || final) && canExecute ? <Button disabled={!instruction.trim() || mutation.isPending || (waiting && draft !== savedDraft)} onClick={() => mutation.mutate('revise')}>优化</Button> : null}
      </Space>
      {waiting && draft !== savedDraft ? <p>请先保存修改，再审核或优化。</p> : null}
    </Modal>
  </>
}
