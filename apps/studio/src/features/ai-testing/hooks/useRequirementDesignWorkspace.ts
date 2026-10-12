import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { requirementDesignApi, type RequirementDesignKind } from '../api/requirementDesign.api'
import { aiTestingApi } from '../api/aiTesting.api'
import { usePersonalLlmChoice } from './usePersonalLlmChoice'
import type { TaskRunDialogRequest } from './useTaskRunDialog'
import type { RequirementAnalysisTaskRun } from '../types'
import { requirementDesignStages } from '../utils/requirementDesign'
import { getErrorMessage } from '@/utils/format'
import { message } from '@/shared/utils/feedback'
import { RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'

const deletes = {
  requirement_analysis: aiTestingApi.deleteRequirementAnalysisRun, function: aiTestingApi.deleteFunctionalCaseGenerateTaskRun,
  api: aiTestingApi.deleteApiCaseGenerateTaskRun, ui: aiTestingApi.deleteUiCaseGenerateTaskRun,
}

export function useRequirementDesignWorkspace(requirementId: string, projectId: string, documentHash: string | undefined, kind: RequirementDesignKind) {
  const client = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedId, setSelectedId] = useState<string>()
  const [configurationIds, setConfigurationIds] = useState<Partial<Record<RequirementDesignKind, string>>>({})
  const [configure, setConfigure] = useState<'save' | 'run'>()
  const [errorContent, setErrorContent] = useState<string>()
  const [dialog, setDialog] = useState<TaskRunDialogRequest>()
  const requestId = useRef<{ taskId: string; options: string; id: string } | undefined>(undefined)
  const configurationRequestIds = useRef<Partial<Record<RequirementDesignKind, string>>>({})
  const personalLlm = usePersonalLlmChoice(projectId)
  const overview = useQuery({ queryKey: ['requirementDesign', requirementId, 'overview'],
    queryFn: () => requirementDesignApi.overview(requirementId), refetchInterval: RUN_HISTORY_POLL_INTERVAL })
  const history = useQuery({ queryKey: ['requirementDesign', requirementId, 'history', kind, page, pageSize, 'all'],
    queryFn: () => requirementDesignApi.history(requirementId, kind, { page, pageSize, pipelineFilter: 'all' }),
    refetchInterval: RUN_HISTORY_POLL_INTERVAL })
  const rows = history.data?.items ?? []
  const tasks = (overview.data?.tasks ?? []).filter(task => task.kind === kind)
  const selectedTaskId = configurationIds[kind] ?? tasks[0]?.taskId
  const selected = rows.find(row => row.runId === selectedId) ?? rows[0] ?? history.data?.latestRun
  const selectedDetail = useQuery({ queryKey: ['requirementDesignSelectedRun', kind, selected?.runId],
    queryFn: async () => await ({ requirement_analysis: aiTestingApi.getRequirementAnalysisRun,
      function: aiTestingApi.getFunctionalCaseGenerateTaskRun, api: aiTestingApi.getApiCaseGenerateTaskRun,
      ui: aiTestingApi.getUiCaseGenerateTaskRun })[kind](selected!.runId!), enabled: Boolean(selected?.runId) })
  const snapshot = selectedDetail.data && 'snapshotJson' in selectedDetail.data
    ? selectedDetail.data.snapshotJson as { documentHash?: string } | undefined : undefined
  const sourceChanged = documentHash && snapshot?.documentHash && documentHash !== snapshot.documentHash
  useEffect(() => {
    const last = Math.max(1, Math.ceil((history.data?.total ?? 0) / pageSize))
    if (history.isSuccess && page > last) setPage(last)
  }, [history.data?.total, history.isSuccess, page, pageSize])
  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: ['requirementDesign', requirementId] })
    void client.invalidateQueries({ queryKey: ['requirement', requirementId] })
  }, [client, requirementId])
  const closeDialog = useCallback(() => { setDialog(undefined); refresh() }, [refresh])
  function open(row: RequirementAnalysisTaskRun, artifact: string, mode: TaskRunDialogRequest['mode'] = 'view') {
    if (artifact === 'errorMessage') { setErrorContent(row.errorMessage); return }
    if (!row.runId || !row.taskId) return
    setSelectedId(row.runId)
    setDialog({ runId: row.runId, taskId: row.taskId, artifact, mode, onClose: closeDialog })
  }
  const start = useMutation({
    mutationFn: async (taskId: string | undefined) => {
      const { connectionId, checkpointEnabled, instruction } = await personalLlm.chooseRun(kind === 'requirement_analysis' || kind === 'function')
      if (!taskId) {
        const configurationRequestId = configurationRequestIds.current[kind] ??= crypto.randomUUID()
        const task = await requirementDesignApi.configure(requirementId, kind, { requestId: configurationRequestId })
        if (!task.taskId) throw new Error('创建生成任务失败，请重试')
        taskId = task.taskId
        setConfigurationIds(previous => ({ ...previous, [kind]: taskId }))
      }
      const options = JSON.stringify({ connectionId, checkpointEnabled, instruction })
      if (requestId.current?.taskId !== taskId || requestId.current.options !== options) requestId.current = { taskId, options, id: crypto.randomUUID() }
      return requirementDesignApi.start(requirementId, kind, { taskId, requestId: requestId.current!.id,
        connectionId, checkpointEnabled, instruction })
    },
    onSuccess: run => { requestId.current = undefined; setSelectedId(run.runId); setPage(1); refresh(); message.success('已发起生成') },
    onError: reason => { if (getErrorMessage(reason) !== '已取消操作') message.error(getErrorMessage(reason)) },
  })
  const remove = useMutation({ mutationFn: (id: string) => deletes[kind](id),
    onSuccess: () => { setSelectedId(undefined); refresh(); message.success('运行记录已删除') }, onError: reason => message.error(getErrorMessage(reason)) })
  const retry = useMutation({ mutationFn: async (row: RequirementAnalysisTaskRun) => {
    const llmConnectionId = await personalLlm.choose()
    if (kind === 'requirement_analysis') return aiTestingApi.retryRequirementAnalysisRunStage(row.runId!, { stage: row.currentStage!, llmConnectionId })
    return aiTestingApi.retryFunctionalCaseGenerateTaskRunStage(row.runId!, { stage: row.currentStage!, llmConnectionId })
  }, onSuccess: refresh, onError: reason => message.error(getErrorMessage(reason)) })
  const graph = useMutation({ mutationFn: async (id: string) => {
    const connectionId = await personalLlm.choose()
    return aiTestingApi.generateFunctionalCaseRelationAnalysis(id, connectionId)
  }, onSuccess: refresh, onError: reason => message.error(getErrorMessage(reason)) })
  const busy = graph.isPending || start.isPending || remove.isPending || retry.isPending
  function run() {
    if ((kind === 'api' || kind === 'ui') && !tasks.find(task => task.taskId === selectedTaskId)?.hasSource) setConfigure('run')
    else start.mutate(selectedTaskId)
  }
  const definitions = requirementDesignStages[kind]
  const generationBlocked = kind === 'function' && !overview.data?.adoptedUnderstanding
  return { kind, overview, tasks, selectedTaskId, selected, definitions, generationBlocked,
    sourceChanged, history, rows, page, setPage, pageSize, setPageSize, start, remove, retry,
    graph, busy, run, refresh, personalLlm, configure, setConfigure, dialog, open, errorContent, setErrorContent,
    resetRunRequest: () => { requestId.current = undefined }, setConfigurationIds, setSelectedId }
}
