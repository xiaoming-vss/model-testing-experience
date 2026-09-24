import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'

const taskRuns = {
  api: {
    task: 'apiCaseGenerateTask', tasks: 'apiCaseGenerateTasks',
    run: 'apiCaseGenerateTaskRun', runs: 'apiCaseGenerateTaskRuns',
    deleteRun: (runId: string) => api.deleteApiCaseGenerateTaskRun(runId),
  },
  functional: {
    task: 'functionalCaseGenerateTask', tasks: 'functionalCaseGenerateTasks',
    run: 'functionalCaseGenerateTaskRun', runs: 'functionalCaseGenerateTaskRuns',
    deleteRun: (runId: string) => api.deleteFunctionalCaseGenerateTaskRun(runId),
  },
  ui: {
    task: 'uiCaseGenerateTask', tasks: 'uiCaseGenerateTasks',
    run: 'uiCaseGenerateTaskRun', runs: 'uiCaseGenerateTaskRuns',
    deleteRun: (runId: string) => api.deleteUiCaseGenerateTaskRun(runId),
  },
  analysis: {
    task: 'requirementAnalysisTask', tasks: 'requirementAnalysisTasks',
    run: 'requirementAnalysisRun', runs: 'requirementAnalysisTaskRuns',
    deleteRun: (runId: string) => api.deleteRequirementAnalysisRun(runId),
  },
  codeRisk: {
    task: 'codeRiskTask', tasks: 'codeRiskTasks',
    run: 'codeRiskRun', runs: 'codeRiskTaskRuns',
    deleteRun: (runId: string) => api.deleteCodeRiskRun(runId),
  },
}

type TaskRunKind = keyof typeof taskRuns

/** 删除成功后才清除当前选中项和精确缓存；各页负责自己的编辑草稿。 */
export function useDeleteTaskRun({ kind, taskId, selectedRunId, onSelectedRunDeleted }: {
  kind: TaskRunKind
  taskId: string
  selectedRunId: string | null | undefined
  onSelectedRunDeleted: () => void
}) {
  const queryClient = useQueryClient()
  const config = taskRuns[kind]

  return useMutation({
    mutationFn: async (runId: string) => { await config.deleteRun(runId) },
    onSuccess: (_data, runId) => {
      message.success('运行记录已删除')
      if (selectedRunId === runId) onSelectedRunDeleted()
      queryClient.removeQueries({ queryKey: [config.run, runId], exact: true })
      queryClient.invalidateQueries({ queryKey: [config.runs, taskId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })
}

/** 执行参数与页面切换由调用方提供；执行后的缓存同步统一维护。 */
export function useStartTaskRun<TInput, TRun extends { runId?: string; projectId?: string }>({
  kind, taskId, projectId, startRun, onStarted,
}: {
  kind: TaskRunKind
  taskId: string
  projectId?: string
  startRun: (input: TInput) => Promise<TRun>
  onStarted: (run: TRun) => void
}) {
  const queryClient = useQueryClient()
  const config = taskRuns[kind]

  return useMutation({
    mutationFn: startRun,
    onSuccess: (run) => {
      message.success(kind === 'analysis' ? '需求分析任务已加入执行队列' : '任务已加入执行队列')
      onStarted(run)
      // UI 和代码风险页原本只刷新运行列表，保留这两类任务的查询契约。
      if (kind !== 'ui' && kind !== 'codeRisk') {
        queryClient.invalidateQueries({ queryKey: [config.task, taskId] })
        queryClient.invalidateQueries({ queryKey: [config.tasks, projectId ?? run.projectId] })
      }
      queryClient.invalidateQueries({ queryKey: [config.runs, taskId] })
    },
    // 其它详情页使用 mutation.error 呈现错误，代码风险页使用消息提示。
    onError: kind === 'codeRisk' ? (error) => message.error(getErrorMessage(error)) : undefined,
  })
}
