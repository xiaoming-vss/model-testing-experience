import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Tooltip } from 'antd'
import { createPortal } from 'react-dom'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { aiTestingApi } from '../api/aiTesting.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { FunctionalCaseRelationsViewer } from './FunctionalCaseRelationsViewer'
import { relationFailed, relationGenerating, useFunctionalCaseRelationsRun } from '../hooks/useFunctionalCaseRelationsRun'

/** 用例图谱弹窗：从功能测试「完整用例」的派生节点打开，图谱绑定该运行的 caseRelations。 */
export function FunctionalCaseRelationsModal({ open, onClose, taskId, runId, disabled, chooseConnection, embedded = false, inspectorContainer, inspectorActionContainer }: {
  embedded?: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  open: boolean
  onClose: () => void
  taskId: string
  runId?: string
  disabled?: boolean
  chooseConnection: () => Promise<string>
}) {
  const client = useQueryClient()
  const runQuery = useFunctionalCaseRelationsRun(runId ?? '', open, false)
  const generating = relationGenerating(runQuery.data)
  const failed = relationFailed(runQuery.data)
  const ready = runQuery.data?.reviewStatus === 'approved' && (runQuery.data.status === 'success' || failed)
  const sidebarMode = embedded && Boolean(inspectorContainer && inspectorActionContainer)
  const graph = useMutation({
    mutationFn: async () => {
      const connectionId = await chooseConnection()
      return aiTestingApi.generateFunctionalCaseRelationAnalysis(runId as string, connectionId)
    },
    onSuccess: async run => {
      client.setQueryData(['functionalCaseGenerateTaskRun', runId], run)
      message.success('已提交图谱生成')
      await client.invalidateQueries({ queryKey: ['functionalCaseGenerateTaskRun', runId] })
    },
    onError: reason => { if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason)) },
  })
  const action = <>
      <Tooltip title={!ready && !generating ? runQuery.isPending ? '正在读取运行状态' : '完整用例审核通过后才能生成图谱' : undefined}>
        <span><Button size="small" loading={graph.isPending || generating} disabled={!runId || disabled || !ready || generating}
          onClick={() => graph.mutate()}>{generating ? '图谱生成中' : failed ? '重新生成图谱' : '生成图谱'}</Button></span>
      </Tooltip>
  </>
  const sidebarActions = open && sidebarMode && inspectorActionContainer ? createPortal(
    <section className="gc-inspector-review gc-inspector-reading-tools"><h3>运行</h3>
      <p className="gc-relations-meta" role="status">{generating ? '图谱生成中，完成后自动刷新' : failed ? '生成失败，可重新运行' : ready ? '完整用例已审核，可生成图谱' : '等待完整用例审核通过'}</p>
      <div className="gc-modal-actions">{action}</div>
    </section>, inspectorActionContainer,
  ) : null
  return <><GenerationArtifactFrame embedded={embedded} hideHeader={sidebarMode} open={open} onCancel={onClose} footer={null}
    width="min(2000px, calc(100vw - 56px))" centered mask={{ closable: false }} destroyOnHidden
    className={`ai-relations-modal generation-chain-relations-modal${sidebarMode ? ' gc-relations-inspector' : ''}`} title="用例图谱">
    {!sidebarMode ? <div className="gc-relations-toolbar">{action}</div> : null}
    {runId ? <div className="gc-relations-body">
      <FunctionalCaseRelationsViewer key={runId} taskId={taskId} runId={runId} embedded={sidebarMode} controlsContainer={inspectorContainer} />
    </div> : null}
  </GenerationArtifactFrame>{sidebarActions}</>
}
