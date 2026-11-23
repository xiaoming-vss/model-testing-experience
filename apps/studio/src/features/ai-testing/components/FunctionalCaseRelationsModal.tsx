import { ARTIFACT_MODAL_WIDTH } from './artifactModalLayout'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Tooltip } from 'antd'
import { createPortal } from 'react-dom'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { usePendingRequestId } from '@/shared/hooks/usePendingRequestId'
import { aiTestingApi } from '../api/aiTesting.api'
import { generationCandidatesApi } from '../api/generationCandidates.api'
import { GenerationArtifactFrame } from './GenerationArtifactFrame'
import { FunctionalCaseRelationsViewer } from './FunctionalCaseRelationsViewer'
import { relationFailed, relationGenerating, relationQueryKey, useFunctionalCaseRelationsRun, type CandidateRelationsSource } from '../hooks/useFunctionalCaseRelationsRun'

/** 用例图谱弹窗：从功能测试「完整用例」的派生节点打开，图谱绑定该运行的 caseRelations。 */
export function FunctionalCaseRelationsModal({ open, onClose, taskId, runId, disabled, chooseConnection, embedded = false, inspectorContainer, inspectorActionContainer, candidate }: {
  embedded?: boolean
  inspectorContainer?: HTMLElement | null
  inspectorActionContainer?: HTMLElement | null
  open: boolean
  onClose: () => void
  taskId: string
  runId?: string
  disabled?: boolean
  chooseConnection: () => Promise<string>
  candidate?: CandidateRelationsSource
}) {
  const client = useQueryClient()
  const pendingRequest = usePendingRequestId()
  const runQuery = useFunctionalCaseRelationsRun(runId ?? '', open, false, candidate)
  const generating = relationGenerating(runQuery.data)
  const failed = relationFailed(runQuery.data)
  const ready = runQuery.data?.reviewStatus === 'approved' && (runQuery.data.status === 'success' || failed)
  const sidebarMode = embedded && Boolean(inspectorContainer && inspectorActionContainer)
  const graph = useMutation({
    mutationFn: async () => {
      const connectionId = await chooseConnection()
      if (candidate) {
        const body = { currentToken: candidate.currentToken, connectionId }
        return generationCandidatesApi.runRelations(candidate.requirementId, { ...body, requestId: pendingRequest.forInput(JSON.stringify(body)) })
      }
      return aiTestingApi.generateFunctionalCaseRelationAnalysis(runId as string, connectionId)
    },
    onSuccess: async run => {
      pendingRequest.clear()
      if (!candidate) client.setQueryData(['functionalCaseGenerateTaskRun', runId], run)
      message.success('已提交图谱生成')
      await client.invalidateQueries({ queryKey: relationQueryKey(runId ?? '', candidate) })
    },
    onError: reason => { if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason)) },
  })
  const action = <>
      <Tooltip title={!ready && !generating ? runQuery.isPending ? '正在读取运行状态' : runQuery.error ? getErrorMessage(runQuery.error) : '完整用例采用后才能生成图谱' : undefined}>
        <span><Button size="small" loading={graph.isPending || generating} disabled={!runId || disabled || !ready || generating}
          onClick={() => graph.mutate()}>{generating ? '图谱生成中' : failed ? '重新生成图谱' : '生成图谱'}</Button></span>
      </Tooltip>
  </>
  const sidebarActions = open && sidebarMode && inspectorActionContainer ? createPortal(
    <section className="gc-inspector-review gc-inspector-reading-tools flex flex-col gap-3 border-t border-[var(--app-surface-border)] bg-[var(--app-list-toolbar-bg)] p-4"><h3 className="m-0 text-[12px] font-semibold">运行</h3>
      <p className="gc-relations-meta m-0 text-[12px] leading-[1.6] text-[var(--app-surface-text-muted)] [overflow-wrap:anywhere]" role="status">{generating ? '图谱生成中，完成后自动刷新' : failed ? '生成失败，可重新运行' : ready ? '完整用例已采用，可生成图谱' : '等待完整用例采用'}</p>
      <div className="gc-modal-actions">{action}</div>
    </section>, inspectorActionContainer,
  ) : null
  return <><GenerationArtifactFrame embedded={embedded} hideHeader={sidebarMode} open={open} onCancel={onClose} footer={null}
    width={ARTIFACT_MODAL_WIDTH} centered mask={{ closable: false }} destroyOnHidden
    className={`ai-relations-modal generation-chain-relations-modal${sidebarMode ? ' gc-relations-inspector' : ''}`} title="用例图谱">
    {!sidebarMode ? <div className="gc-relations-toolbar flex items-center justify-end gap-3 pb-2.5">{action}</div> : null}
    {runId ? <div className={`gc-relations-body${sidebarMode ? ' flex min-h-0 flex-1 overflow-hidden' : ' h-[min(76dvh,900px)] min-h-[360px]'}`}>
      <FunctionalCaseRelationsViewer key={runId} taskId={taskId} runId={runId} embedded={sidebarMode} controlsContainer={inspectorContainer} candidate={candidate} />
    </div> : null}
  </GenerationArtifactFrame>{sidebarActions}</>
}
