import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form } from 'antd'
import type { InputRef } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { api } from '@/services/api'
import type { JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import { goBackOrFallback } from '@/shared/utils/backNavigation'
import { message } from '@/shared/utils/feedback'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId,
  pickUpdatedAt,
} from '@/utils/format'
import {
  EMPTY_API_CASES,
  buildApiCaseUpdatePayload,
  createDefaultCaseFormValues,
  getCaseId,
  type ApiCaseFormValues,
} from '../utils/apiCaseEditor'
import { isApiRunPollingStatus } from '../utils/detailView'
import { useApiCaseImport } from './useApiCaseImport'
import { useApiCaseState } from './useApiCaseState'
import { useApiCollectionData } from './useApiCollectionData'
import { useApiCollectionRunReport } from './useApiCollectionRunReport'
import { useApiEditorSplitter } from './useApiEditorSplitter'
import { useApiEnvVarPicker } from './useApiEnvVarPicker'
import { useApiExecution } from './useApiExecution'
import { useApiRuleEditing } from './useApiRuleEditing'

export function useApiCollectionDetailPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { collectionId = '' } = useParams()
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [environmentPopoverOpen, setEnvironmentPopoverOpen] = useState(false)
  const [caseForm] = Form.useForm<ApiCaseFormValues>()
  const pathInputRef = useRef<InputRef | null>(null)
  const bodyJsonEditorRef = useRef<JsonEditorRef | null>(null)

  const data = useApiCollectionData({ collectionId, selectedEnvironmentId, selectedCaseId })
  const cases = data.casesQuery.data ?? EMPTY_API_CASES
  const { can } = useProjectAccess(data.projectId ?? '')
  const rules = useApiRuleEditing({ activeCaseId: data.activeCaseId })
  const execution = useApiExecution({ collectionId })
  const caseState = useApiCaseState({
    collectionId,
    cases,
    caseForm,
    queryClient,
    can,
    activeCaseId: data.activeCaseId,
    selectedCaseId,
    setSelectedCaseId,
    selectedCaseDetail: data.selectedCaseDetailQuery.data,
  })
  const caseImport = useApiCaseImport({ collectionId })
  const envPicker = useApiEnvVarPicker({
    caseForm,
    resolvedEnvironmentId: data.resolvedEnvironmentId,
    environmentVars: data.environmentVars,
    environmentVarsQuery: data.environmentVarsQuery,
    bodyJsonEditorRef,
  })
  const splitter = useApiEditorSplitter({ hasRunResult: Boolean(execution.runResult) })

  const setCaseEditingCase = caseState.setEditingCase
  const setCaseDraftCaseValues = caseState.setDraftCaseValues
  const setExecutionRunResult = execution.setRunResult
  const setActiveApiCaseRunId = execution.setActiveApiCaseRunId
  const setRunResultView = execution.setRunResultView
  const resetApiCaseRunStatus = execution.resetApiCaseRunStatus
  const setSelectedCollectionRunId = execution.setSelectedCollectionRunId
  const setCollectionRunReportOpen = execution.setCollectionRunReportOpen
  const setCollectionRunHistoryOpen = execution.setCollectionRunHistoryOpen
  const setActivePollingCollectionRunId = execution.setActivePollingCollectionRunId
  const resetActiveCollectionRunStatus = execution.resetActiveCollectionRunStatus

  useEffect(() => {
    if (data.environments.length === 0) {
      if (selectedEnvironmentId) setSelectedEnvironmentId(undefined)
      return
    }

    const selectedExists = selectedEnvironmentId
      ? data.environments.some((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId)
      : false

    if (selectedExists) return

    const fallbackEnvironment = data.environments.find((environment) => environment.isDefault) ?? data.environments[0]
    const fallbackEnvironmentId = fallbackEnvironment ? normalizeEnvironmentId(fallbackEnvironment) : undefined
    if (fallbackEnvironmentId !== selectedEnvironmentId) {
      setSelectedEnvironmentId(fallbackEnvironmentId)
    }
  }, [data.environments, selectedEnvironmentId])

  useEffect(() => {
    setCaseEditingCase(null)
    setCaseDraftCaseValues(null)
    setSelectedCaseId('')
    setExecutionRunResult(null)
    setActiveApiCaseRunId('')
    setRunResultView('response')
    resetApiCaseRunStatus()
    caseForm.setFieldsValue(createDefaultCaseFormValues())
  }, [caseForm, collectionId, resetApiCaseRunStatus, setActiveApiCaseRunId, setCaseDraftCaseValues, setCaseEditingCase, setExecutionRunResult, setRunResultView])

  useEffect(() => {
    setSelectedCollectionRunId('')
    setCollectionRunReportOpen(false)
    setCollectionRunHistoryOpen(false)
    setActivePollingCollectionRunId('')
    resetActiveCollectionRunStatus()
  }, [collectionId, resetActiveCollectionRunStatus, setActivePollingCollectionRunId, setCollectionRunHistoryOpen, setCollectionRunReportOpen, setSelectedCollectionRunId])

  const switchDefaultEnvironmentMutation = useMutation({
    mutationFn: async (nextEnvironmentId: string) => {
      const nextEnvironment = data.environments.find((environment) => normalizeEnvironmentId(environment) === nextEnvironmentId)
      if (!nextEnvironment) throw new Error('未找到所选环境')

      const currentDefaultEnvironment = data.environments.find((environment) => environment.isDefault)
      const currentDefaultEnvironmentId = currentDefaultEnvironment ? normalizeEnvironmentId(currentDefaultEnvironment) : undefined
      const requests: Array<Promise<unknown>> = []

      if (currentDefaultEnvironmentId && currentDefaultEnvironmentId !== nextEnvironmentId) {
        requests.push(api.updateApiEnvironment(currentDefaultEnvironmentId, { isDefault: false }))
      }

      if (!nextEnvironment.isDefault) {
        requests.push(api.updateApiEnvironment(nextEnvironmentId, { isDefault: true }))
      }

      if (requests.length > 0) await Promise.all(requests)
      return nextEnvironmentId
    },
    onMutate: async (nextEnvironmentId) => {
      const previousEnvironmentId = selectedEnvironmentId
      setSelectedEnvironmentId(nextEnvironmentId)
      setEnvironmentPopoverOpen(false)
      return { previousEnvironmentId }
    },
    onError: (error, _nextEnvironmentId, context) => {
      setSelectedEnvironmentId(context?.previousEnvironmentId)
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['testEnvironments', data.projectId, 'api'] })
    },
  })

  function handleSelectEnvironment(nextEnvironmentId: string) {
    if (!nextEnvironmentId || nextEnvironmentId === data.resolvedEnvironmentId) {
      setEnvironmentPopoverOpen(false)
      return
    }

    switchDefaultEnvironmentMutation.mutate(nextEnvironmentId)
  }

  async function handleSendRequest() {
    try {
      if (!data.resolvedEnvironmentId) {
        message.warning('请先选择可用环境')
        return
      }

      if (caseState.isCreatingCase) {
        message.warning('请先保存用例后再发送')
        return
      }

      if (!caseState.editingCase || getCaseId(caseState.editingCase) !== data.activeCaseId) {
        message.warning('用例详情加载中，请稍后再试')
        return
      }

      await caseForm.validateFields()
      const values = caseState.getCompleteCaseFormValues()
      const payload = buildApiCaseUpdatePayload(caseState.editingCase, values)

      if (Object.keys(payload).length > 0) {
        message.warning('当前有未保存修改，请先保存后再发送')
        return
      }

      await execution.runApiCaseMutation.mutateAsync({ caseId: data.activeCaseId, environmentId: data.resolvedEnvironmentId })
    } catch (error) {
      if (error instanceof Error) {
        message.error(getErrorMessage(error))
      }
      // validation errors are shown by the form
    }
  }

  async function handleRunCollection() {
    if (!collectionId) return
    if (!data.resolvedEnvironmentId) {
      message.warning('请先选择可用环境')
      return
    }
    if (cases.length === 0) {
      message.warning('当前 Collection 还没有可运行的用例')
      return
    }

    try {
      await execution.runApiCollectionMutation.mutateAsync({ collectionId, environmentId: data.resolvedEnvironmentId })
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const runReport = useApiCollectionRunReport({
    collectionId,
    queryClient,
    environments: data.environments,
    collectionName: data.collectionQuery.data?.name || 'API测试集',
    execution,
  })

  const runResultStatus = execution.runResult?.status ?? (execution.runResult ? (execution.runResult.success ? 'success' : 'failed') : undefined)
  const isApiCaseRunInProgress = isApiRunPollingStatus(runResultStatus)
  const postOperationCount = rules.assertRules.length + rules.extractRules.length

  const isSelectedCaseReady = caseState.isCreatingCase || (Boolean(data.activeCaseId) && (caseState.editingCase ? getCaseId(caseState.editingCase) === data.activeCaseId : false))

  /* Query 参数页签靠末尾空行新增，所以编辑中始终保证 query 列表末尾有一行空行。
     请求头页签有自己的虚线新增行，不再需要这一行。 */
  const ensureQueryTrailingRow = useCallback((items?: Array<{ enabled?: boolean; key?: string; value?: string }>) => {
    const rows = items ?? []
    if (rows.length === 0) {
      caseForm.setFieldValue('query', [{ enabled: false, key: '', value: '' }])
      return
    }

    const nextRows = rows.map((row) => {
      const hasContent = Boolean((row.key ?? '').trim() || (row.value ?? '').trim())
      if (hasContent && row.enabled === false) {
        return { ...row, enabled: true }
      }
      return row
    })

    const lastRow = nextRows[nextRows.length - 1]
    if ((lastRow?.key ?? '').trim() || (lastRow?.value ?? '').trim()) {
      caseForm.setFieldValue('query', [...nextRows, { enabled: false, key: '', value: '' }])
      return
    }

    const changed = JSON.stringify(rows) !== JSON.stringify(nextRows)
    if (changed) caseForm.setFieldValue('query', nextRows)
  }, [caseForm])

  return {
    collectionId,
    navigate,
    queryClient,
    selectedEnvironmentId,
    environmentPopoverOpen,
    setEnvironmentPopoverOpen,
    caseForm,
    pathInputRef,
    bodyJsonEditorRef,
    cases,
    ...data,
    can,
    ...rules,
    ...execution,
    ...caseState,
    ...caseImport,
    ...envPicker,
    envVarPicker: envPicker,
    ...splitter,
    ensureQueryTrailingRow,
    switchDefaultEnvironmentMutation,
    handleSelectEnvironment,
    handleSendRequest,
    handleRunCollection,
    ...runReport,
    runResultStatus,
    isApiCaseRunInProgress,
    postOperationCount,
    isSelectedCaseReady,
    updatedAtText: data.collectionQuery.data ? formatTime(pickUpdatedAt(data.collectionQuery.data)) : '-',
    onBack: () => goBackOrFallback(navigate, '/testing?tab=api'),
    selectedCaseCount: cases.length,
  } as const
}

export type ApiCollectionDetailPageModel = ReturnType<typeof useApiCollectionDetailPage>
