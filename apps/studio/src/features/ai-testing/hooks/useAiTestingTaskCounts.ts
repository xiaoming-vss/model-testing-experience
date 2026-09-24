import { useQuery } from '@tanstack/react-query'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { api, listItems } from '@/services/api'

/**
 * 模块导航（任务 / Skill库）上的计数徽标。
 *
 * 取的是和任务列表同一批查询（queryKey 一致，react-query 会与列表页的请求去重），
 * 所以这里不另建缓存，也不额外引入状态——计数天然跟着列表走。
 * 迭代范围与列表页保持一致：都按当前迭代过滤，否则徽标会显示比列表更多的条目。
 */
export function useAiTestingTaskCounts(activeProjectId: string | undefined) {
  const { activeSprintId } = useActiveSprint()
  const enabled = Boolean(activeProjectId)
  const inActiveSprint = (sprintId?: string) => !activeSprintId || sprintId === activeSprintId

  const apiTasks = useQuery({
    queryKey: ['apiCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getApiCaseGenerateTasks(activeProjectId!),
    enabled,
  })
  const functionalTasks = useQuery({
    queryKey: ['functionalCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getFunctionalCaseGenerateTasks(activeProjectId!),
    enabled,
  })
  const uiTasks = useQuery({
    queryKey: ['uiCaseGenerateTasks', activeProjectId],
    queryFn: () => api.getUiCaseGenerateTasks(activeProjectId!),
    enabled,
  })
  const analysisTasks = useQuery({
    queryKey: ['requirementAnalysisTasks', activeProjectId],
    queryFn: () => api.getRequirementAnalysisTasks(activeProjectId!),
    enabled,
  })
  const codeRiskTasks = useQuery({
    queryKey: ['codeRiskTasks', activeProjectId],
    queryFn: () => api.getCodeRiskTasks(activeProjectId!),
    enabled,
  })
  const queries = { api: apiTasks, functional: functionalTasks, ui: uiTasks, analysis: analysisTasks, codeRisk: codeRiskTasks }
  const kindCounts = Object.fromEntries(Object.entries(queries).map(([kind, query]) => [
    kind, listItems(query.data).filter((task) => inActiveSprint(task.sprintId)).length,
  ]))
  return { kindCounts }
}
