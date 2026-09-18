import { ActionButton } from '@/shared/components/ActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ArrowLeftOutlined, CheckOutlined, CodeOutlined, CodeSandboxOutlined, DownOutlined, InfoCircleOutlined, FunctionOutlined, PlusOutlined, SearchOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Dropdown, Empty, Form, Input, InputNumber, Modal, Popconfirm, Popover, Segmented, Select, Space, Switch, Tabs, Tag, Tooltip, Typography, Upload } from 'antd'
import type { InputRef } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { JsonEditor, type JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import {
  assertComparatorLabelMap,
  assertComparatorOptions,
  assertSourceLabelMap,
  assertSourceOptions,
  bodyTypeOptions,
  builtinTemplateFunctions,
  collectionReportViewOptions,
  DRAFT_CASE_ID,
  ENV_VAR_TOKEN_PREFIX,
  ENV_VAR_TOKEN_SUFFIX,
  extractSourceLabelMap,
  extractSourceOptions,
  methodOptions,
  methodTagColor,
  MIN_EDITOR_RESULT_HEIGHT,
  MIN_EDITOR_TOP_HEIGHT,
  runResultViewOptions,
  type CollectionReportView,
  type EnvVarPickerMode,
  type RunResultView,
} from '../config/collectionConfig'
import {
  buildApiCaseUpdatePayload,
  buildCaseFormValues,
  createDefaultCaseFormValues,
  EMPTY_API_CASES,
  EMPTY_API_ENVIRONMENTS,
  EMPTY_ASSERT_RULES,
  EMPTY_EXTRACT_RULES,
  formatOptionalValue,
  getCaseDisplayPath,
  getCaseId,
  getCollectionRunItemKey,
  mergeApiCaseWithFormValues,
  mergeDefinedApiCaseFields,
  moveArrayItem,
  parseMaybeJsonValue,
  serializeCaseValues,
  sortCasesByOrderNo,
  sortRulesByOrderNo,
  type ApiCaseFormValues,
} from '../utils/apiCaseEditor'
import { buildCollectionRunReportHtml, getExecutionStatusMeta, sanitizeFileName } from '../utils/collectionRunReport'
import {
  api,
  listItems,
  type ApiAssertComparator,
  type ApiAssertRule,
  type ApiAssertSource,
  type ApiCase,
  type ApiCaseRunResult,
  type ApiCollectionRunReport,
  type ApiCollectionRunSummary,
  type ApiExtractRule,
  type CreateApiAssertRulePayload,
  type CreateApiExtractRulePayload,
} from '@/services/api'
import {
  formatTime,
  getErrorMessage,
  normalizeAssertRuleId,
  normalizeEnvironmentId,
  normalizeExtractRuleId,
  pickUpdatedAt,
} from '@/utils/format'
import { buildApiAssertRuleUpdatePayload, buildApiExtractRuleUpdatePayload } from '@/utils/updatePayload'
import { message } from '@/shared/utils/feedback'

const { Text } = Typography

type AssertRuleFormValues = CreateApiAssertRulePayload
type ExtractRuleFormValues = CreateApiExtractRulePayload
type CaseImportMode = 'upload' | 'editor'

const API_RUN_TERMINAL_STATUSES = ['success', 'failed', 'error'] as const

function isApiRunPollingStatus(status?: string) {
  return status === 'pending' || status === 'running'
}

function isApiRunTerminalStatus(status?: string) {
  return API_RUN_TERMINAL_STATUSES.includes(status as typeof API_RUN_TERMINAL_STATUSES[number])
}

function getApiCaseRunId(run?: ApiCaseRunResult | null) {
  return run?.runId ?? run?.caseRunId ?? run?.run_id ?? run?.case_run_id ?? ''
}

function validateJsonText(value?: string) {
  if (!value?.trim()) return Promise.resolve()

  try {
    JSON.parse(value)
    return Promise.resolve()
  } catch (error) {
    return Promise.reject(error instanceof Error ? error.message : 'JSON 格式不正确')
  }
}

function isYamlFileName(fileName: string) {
  return /\.(yaml|yml)$/i.test(fileName.trim())
}

export function ApiCollectionDetailPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { collectionId = '' } = useParams()
  const [editingCase, setEditingCase] = useState<ApiCase | null>(null)
  const [draftCaseValues, setDraftCaseValues] = useState<ApiCaseFormValues | null>(null)
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [caseSearch, setCaseSearch] = useState('')
  const [caseOrderIds, setCaseOrderIds] = useState<string[]>([])
  const [draggingCaseId, setDraggingCaseId] = useState<string | null>(null)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [environmentPopoverOpen, setEnvironmentPopoverOpen] = useState(false)
  const [envVarPickerOpenKey, setEnvVarPickerOpenKey] = useState<string | null>(null)
  const [envVarPickerMode, setEnvVarPickerMode] = useState<EnvVarPickerMode>('environment')
  const [envVarPickerSearch, setEnvVarPickerSearch] = useState('')
  const [envVarPickerSelectedKey, setEnvVarPickerSelectedKey] = useState<string>('')
  const envVarPickerInsertHandlersRef = useRef<Record<string, (templateText: string) => void>>({})
  const [runResult, setRunResult] = useState<ApiCaseRunResult | null>(null)
  const [activeApiCaseRunId, setActiveApiCaseRunId] = useState('')
  const [runResultView, setRunResultView] = useState<RunResultView>('response')
  const [collectionRunReportOpen, setCollectionRunReportOpen] = useState(false)
  const [collectionRunHistoryOpen, setCollectionRunHistoryOpen] = useState(false)
  const [selectedCollectionRunId, setSelectedCollectionRunId] = useState('')
  const [activePollingCollectionRunId, setActivePollingCollectionRunId] = useState('')
  const [loadingCollectionRunHistoryId, setLoadingCollectionRunHistoryId] = useState('')
  const [refreshingCollectionRunReport, setRefreshingCollectionRunReport] = useState(false)
  const [collectionRunReportView, setCollectionRunReportView] = useState<CollectionReportView>('items')
  const [expandedCollectionRunItemIds, setExpandedCollectionRunItemIds] = useState<string[]>([])
  const [collectionRunItemViews, setCollectionRunItemViews] = useState<Record<string, RunResultView>>({})
  const [assertRuleModalOpen, setAssertRuleModalOpen] = useState(false)
  const [extractRuleModalOpen, setExtractRuleModalOpen] = useState(false)
  const [editingAssertRule, setEditingAssertRule] = useState<ApiAssertRule | null>(null)
  const [editingExtractRule, setEditingExtractRule] = useState<ApiExtractRule | null>(null)
  const [caseImportModalOpen, setCaseImportModalOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importYamlFile, setImportYamlFile] = useState<File | null>(null)
  const [importYamlText, setImportYamlText] = useState('')
  const [editorTopHeight, setEditorTopHeight] = useState(520)
  const [isResizingEditor, setIsResizingEditor] = useState(false)
  const [caseForm] = Form.useForm<ApiCaseFormValues>()
  const [assertRuleForm] = Form.useForm<AssertRuleFormValues>()
  const [extractRuleForm] = Form.useForm<ExtractRuleFormValues>()
  const caseOrderRollbackRef = useRef<string[]>([])
  const pathInputRef = useRef<InputRef | null>(null)
  const envVarInputRefs = useRef<Record<string, InputRef | null>>({})
  const bodyJsonEditorRef = useRef<JsonEditorRef | null>(null)
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)
  const editorResizeRef = useRef<{ startY: number; startHeight: number } | null>(null)
  const previousApiCaseRunStatusRef = useRef<ApiCaseRunResult['status'] | ''>('')
  const previousActiveRunStatusRef = useRef<ApiCollectionRunSummary['status'] | ''>('')
  const watchedBodyType = Form.useWatch('bodyType', caseForm)
  const watchedQuery = Form.useWatch('query', caseForm)
  const watchedHeaders = Form.useWatch('headers', caseForm)
  const watchedAssertSource = Form.useWatch('assertSource', assertRuleForm)
  const watchedAssertComparator = Form.useWatch('comparator', assertRuleForm)
  const watchedExtractSource = Form.useWatch('source', extractRuleForm)
  const isCreatingCase = selectedCaseId === DRAFT_CASE_ID

  function getCompleteCaseFormValues() {
    const allValues = caseForm.getFieldsValue(true) as Partial<ApiCaseFormValues>

    return {
      ...createDefaultCaseFormValues(),
      ...allValues,
      headers: allValues.headers ?? [{ enabled: false, key: '', value: '' }],
      query: allValues.query ?? [{ enabled: false, key: '', value: '' }],
    } satisfies ApiCaseFormValues
  }

  const collectionQuery = useQuery({
    queryKey: ['apiCollection', collectionId],
    queryFn: () => api.getApiCollection(collectionId),
    enabled: Boolean(collectionId),
  })
  const casesQuery = useQuery({
    queryKey: ['apiCases', collectionId],
    queryFn: () => api.getApiCases(collectionId),
    enabled: Boolean(collectionId),
  })

  const requirementId = collectionQuery.data?.requirementId ?? collectionQuery.data?.requirement_id
  const requirementQuery = useQuery({
    queryKey: ['requirement', requirementId],
    queryFn: () => api.getRequirement(requirementId!),
    enabled: Boolean(requirementId),
  })
  const sprintId = requirementQuery.data?.sprintId ?? requirementQuery.data?.sprint_id
  const sprintQuery = useQuery({
    queryKey: ['sprint', sprintId],
    queryFn: () => api.getSprint(sprintId!),
    enabled: Boolean(sprintId),
  })
  const projectId = sprintQuery.data?.projectId ?? sprintQuery.data?.project_id
  const { can } = useProjectAccess(projectId ?? '')
  const environmentsQuery = useQuery({
    queryKey: ['apiEnvironments', projectId],
    queryFn: () => api.getApiEnvironments(projectId!),
    enabled: Boolean(projectId),
  })
  const environments = environmentsQuery.data ?? EMPTY_API_ENVIRONMENTS
  const selectedEnvironment =
    environments.find((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId) ??
    environments.find((environment) => environment.isDefault) ??
    environments[0]
  const resolvedEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined
  const environmentVarsQuery = useQuery({
    queryKey: ['apiEnvironmentVars', resolvedEnvironmentId],
    queryFn: () => api.getApiEnvironmentVars(resolvedEnvironmentId!),
    enabled: Boolean(resolvedEnvironmentId),
  })
  const environmentVars = useMemo(() => environmentVarsQuery.data ?? [], [environmentVarsQuery.data])
  const activeCaseId = selectedCaseId && selectedCaseId !== DRAFT_CASE_ID ? selectedCaseId : ''
  const selectedCaseDetailQuery = useQuery({
    queryKey: ['apiCase', activeCaseId],
    queryFn: () => api.getApiCase(activeCaseId),
    enabled: Boolean(activeCaseId),
    refetchOnWindowFocus: false,
  })
  const activeApiCaseRunQuery = useQuery({
    queryKey: ['apiCaseRun', activeApiCaseRunId],
    queryFn: () => api.getApiCaseRun(activeApiCaseRunId),
    enabled: Boolean(activeApiCaseRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCaseRunResult | undefined
      return !data || isApiRunPollingStatus(data.status) ? 1500 : false
    },
  })
  const isSelectedCaseReady = isCreatingCase || (Boolean(activeCaseId) && (editingCase ? getCaseId(editingCase) === activeCaseId : false))
  const filteredEnvironmentVars = useMemo(() => {
    const keyword = envVarPickerSearch.trim().toLowerCase()
    if (!keyword) return environmentVars
    return environmentVars.filter((item) => item.varKey.toLowerCase().includes(keyword))
  }, [envVarPickerSearch, environmentVars])
  const filteredBuiltinTemplateFunctions = useMemo(() => {
    const keyword = envVarPickerSearch.trim().toLowerCase()
    if (!keyword) return builtinTemplateFunctions
    return builtinTemplateFunctions.filter((item) =>
      [item.label, item.token, item.description, item.example].filter(Boolean).some((field) => field!.toLowerCase().includes(keyword)),
    )
  }, [envVarPickerSearch])
  const collectionRunHistoryQuery = useQuery({
    queryKey: ['apiCollectionRuns', collectionId],
    queryFn: () => api.getApiCollectionRuns(collectionId),
    enabled: Boolean(collectionId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = (query.state.data as ApiCollectionRunSummary[] | undefined) ?? []
      return data.some((item) => isApiRunPollingStatus(item.status)) ? 3000 : false
    },
  })
  const activeCollectionRunQuery = useQuery({
    queryKey: ['apiCollectionRun', activePollingCollectionRunId],
    queryFn: () => api.getApiCollectionRun(activePollingCollectionRunId),
    enabled: Boolean(activePollingCollectionRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCollectionRunSummary | undefined
      return !data || isApiRunPollingStatus(data.status) ? 3000 : false
    },
  })
  const collectionRunReportQuery = useQuery({
    queryKey: ['apiCollectionRunReport', selectedCollectionRunId],
    queryFn: () => api.getApiCollectionRunReport(selectedCollectionRunId),
    enabled: collectionRunReportOpen && Boolean(selectedCollectionRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as ApiCollectionRunReport | undefined
      return collectionRunReportOpen && (!data || isApiRunPollingStatus(data.status)) && Boolean(selectedCollectionRunId) ? 3000 : false
    },
  })

  useEffect(() => {
    if (environments.length === 0) {
      if (selectedEnvironmentId) setSelectedEnvironmentId(undefined)
      return
    }

    const selectedExists = selectedEnvironmentId
      ? environments.some((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId)
      : false

    if (selectedExists) return

    const fallbackEnvironment = environments.find((environment) => environment.isDefault) ?? environments[0]
    const fallbackEnvironmentId = fallbackEnvironment ? normalizeEnvironmentId(fallbackEnvironment) : undefined
    if (fallbackEnvironmentId !== selectedEnvironmentId) {
      setSelectedEnvironmentId(fallbackEnvironmentId)
    }
  }, [environments, selectedEnvironmentId])

  useEffect(() => {
    if (!envVarPickerOpenKey) return
    if (envVarPickerMode === 'builtin') {
      if (filteredBuiltinTemplateFunctions.some((item) => item.token === envVarPickerSelectedKey)) return
      setEnvVarPickerSelectedKey(filteredBuiltinTemplateFunctions[0]?.token ?? '')
      return
    }

    const environmentTokens = filteredEnvironmentVars.map((item) => formatEnvironmentToken(item.varKey))
    if (environmentTokens.includes(envVarPickerSelectedKey)) return
    setEnvVarPickerSelectedKey(environmentTokens[0] ?? '')
  }, [envVarPickerMode, envVarPickerOpenKey, envVarPickerSelectedKey, filteredBuiltinTemplateFunctions, filteredEnvironmentVars])

  useEffect(() => {
    setEditingCase(null)
    setDraftCaseValues(null)
    setSelectedCaseId('')
    setRunResult(null)
    setActiveApiCaseRunId('')
    setRunResultView('response')
    previousApiCaseRunStatusRef.current = ''
    caseForm.setFieldsValue(createDefaultCaseFormValues())
  }, [caseForm, collectionId])

  useEffect(() => {
    setSelectedCollectionRunId('')
    setCollectionRunReportOpen(false)
    setCollectionRunHistoryOpen(false)
    setActivePollingCollectionRunId('')
    previousActiveRunStatusRef.current = ''
  }, [collectionId])

  useEffect(() => {
    const currentRun = activeCollectionRunQuery.data
    if (!currentRun?.collectionRunId) return

    queryClient.setQueryData<ApiCollectionRunSummary[]>(['apiCollectionRuns', collectionId], (current) => {
      const currentItems = current ?? []
      const nextItems = [currentRun, ...currentItems.filter((item) => item.collectionRunId !== currentRun.collectionRunId)]
      return nextItems.sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      })
    })

    const previousStatus = previousActiveRunStatusRef.current
    previousActiveRunStatusRef.current = currentRun.status ?? ''
    if (isApiRunPollingStatus(currentRun.status)) return
    if (previousStatus === currentRun.status) return

    setActivePollingCollectionRunId('')
    queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
    if (currentRun.status === 'success') {
      message.success('测试运行完成')
      return
    }
    if (currentRun.status === 'failed' || currentRun.status === 'error') {
      message.error(currentRun.errorMessage || '测试运行完成，存在失败项')
    }
  }, [activeCollectionRunQuery.data, collectionId, queryClient])

  useEffect(() => {
    const currentRun = activeApiCaseRunQuery.data
    const currentRunId = getApiCaseRunId(currentRun) || activeApiCaseRunId
    if (!currentRun || !currentRunId) return

    const normalizedRun = { ...currentRun, runId: currentRunId }
    setRunResult(normalizedRun)
    const previousStatus = previousApiCaseRunStatusRef.current
    previousApiCaseRunStatusRef.current = normalizedRun.status ?? ''

    if (isApiRunPollingStatus(normalizedRun.status)) return
    if (!isApiRunTerminalStatus(normalizedRun.status)) return
    if (previousStatus === normalizedRun.status) return

    setActiveApiCaseRunId('')
    if (normalizedRun.environmentId) {
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', normalizedRun.environmentId] })
    }

    if (normalizedRun.status === 'success') {
      message.success('运行完成')
      return
    }
    if (normalizedRun.status === 'failed') {
      message.error(normalizedRun.errorMessage || '运行完成，断言失败')
      return
    }
    message.error(normalizedRun.errorMessage || '运行异常')
  }, [activeApiCaseRunId, activeApiCaseRunQuery.data, queryClient])

  useEffect(() => {
    if (!activeApiCaseRunId || !activeApiCaseRunQuery.error) return

    const errorMessage = getErrorMessage(activeApiCaseRunQuery.error)
    setRunResult((currentRun) => ({
      ...(currentRun ?? {}),
      runId: getApiCaseRunId(currentRun) || activeApiCaseRunId,
      status: 'error',
      errorMessage: currentRun?.errorMessage || errorMessage,
    }))
    previousApiCaseRunStatusRef.current = 'error'
    setActiveApiCaseRunId('')
    message.error(errorMessage)
  }, [activeApiCaseRunId, activeApiCaseRunQuery.error])

  useEffect(() => {
    const report = collectionRunReportQuery.data
    if (!report) return

    const orderedItems = [...(report.items ?? [])].sort((left, right) => {
      const leftOrderNo = left.orderNo ?? Number.MAX_SAFE_INTEGER
      const rightOrderNo = right.orderNo ?? Number.MAX_SAFE_INTEGER
      if (leftOrderNo !== rightOrderNo) return leftOrderNo - rightOrderNo
      return (left.caseName ?? '').localeCompare(right.caseName ?? '')
    })
    const firstExpandedIndex = orderedItems.findIndex(
      (item) => item.status === 'failed' || item.status === 'error' || isApiRunPollingStatus(item.status),
    )
    const fallbackExpandedIndex = firstExpandedIndex >= 0 ? firstExpandedIndex : orderedItems.length > 0 ? 0 : -1
    const firstExpandedItem = fallbackExpandedIndex >= 0 ? orderedItems[fallbackExpandedIndex] : undefined

    setCollectionRunReportView('items')
    setExpandedCollectionRunItemIds(firstExpandedItem ? [getCollectionRunItemKey(firstExpandedItem, fallbackExpandedIndex)] : [])
    setCollectionRunItemViews({})
  }, [collectionRunReportQuery.data])

  useEffect(() => {
    if (!selectedCollectionRunId) {
      if (loadingCollectionRunHistoryId) setLoadingCollectionRunHistoryId('')
      return
    }
    if (collectionRunReportQuery.isFetching) return
    if (loadingCollectionRunHistoryId === selectedCollectionRunId) {
      setLoadingCollectionRunHistoryId('')
    }
  }, [collectionRunReportQuery.isFetching, loadingCollectionRunHistoryId, selectedCollectionRunId])

  function syncCaseDetailState(apiCase: ApiCase) {
    const caseId = getCaseId(apiCase)
    setEditingCase(apiCase)
    setSelectedCaseId(caseId)
    caseForm.setFieldsValue(buildCaseFormValues(apiCase))
    queryClient.setQueryData(['apiCase', caseId], apiCase)
  }

  async function resolveCompleteCaseAfterSave(savedCase: ApiCase, submittedValues: ApiCaseFormValues, previousCase?: ApiCase | null) {
    const caseId = getCaseId(savedCase)
    const optimisticCase = mergeDefinedApiCaseFields(mergeApiCaseWithFormValues(previousCase ?? savedCase, submittedValues), savedCase)

    if (!caseId) return optimisticCase

    try {
      return await api.getApiCase(caseId)
    } catch {
      return optimisticCase
    }
  }

  const createCaseMutation = useMutation({
    mutationFn: (values: ApiCaseFormValues) =>
      api.createApiCase(collectionId, {
        ...serializeCaseValues(values),
        orderNo: 1,
      }),
    onSuccess: async (createdCase, values) => {
      const createdCaseId = getCaseId(createdCase)
      const currentOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : sortCasesByOrderNo(cases).map((item) => getCaseId(item))).filter(Boolean)
      const nextOrderIds = [createdCaseId, ...currentOrderIds.filter((id) => id !== createdCaseId)]
      const completeCase = await resolveCompleteCaseAfterSave(createdCase, values)

      message.success('用例已创建')
      setDraftCaseValues(null)
      syncCaseDetailState(completeCase)
      caseOrderRollbackRef.current = caseOrderIds
      setCaseOrderIds(nextOrderIds)
      reorderCasesMutation.mutate(nextOrderIds)

      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const updateCaseMutation = useMutation({
    mutationFn: (values: ApiCaseFormValues) => {
      const payload = buildApiCaseUpdatePayload(editingCase!, values)
      if (Object.keys(payload).length === 0) {
        return Promise.resolve(editingCase!)
      }

      return api.updateApiCase(getCaseId(editingCase!), payload)
    },
    onSuccess: async (updatedCase, values) => {
      const completeCase = await resolveCompleteCaseAfterSave(updatedCase, values, editingCase)

      message.success('用例已更新')
      syncCaseDetailState(completeCase)
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deleteApiCase(caseId),
    onSuccess: (_, caseId) => {
      message.success('用例已删除')
      setCaseOrderIds((current) => current.filter((id) => id !== caseId))
      setSelectedCaseId((current) => (current === caseId ? '' : current))
      queryClient.removeQueries({ queryKey: ['apiCase', caseId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
  })

  const reorderCasesMutation = useMutation({
    mutationFn: async (nextOrderIds: string[]) => {
      const caseMap = new Map(cases.map((item) => [getCaseId(item), item]))

      await Promise.all(
        nextOrderIds.map((caseId, index) => {
          const targetCase = caseMap.get(caseId)
          const nextOrderNo = index + 1

          if (targetCase?.orderNo === nextOrderNo) return Promise.resolve()
          return api.updateApiCase(caseId, { orderNo: nextOrderNo })
        }),
      )
    },
    onSuccess: () => {
      message.success('用例顺序已更新')
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
    onError: (error) => {
      setCaseOrderIds(caseOrderRollbackRef.current)
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      caseOrderRollbackRef.current = []
      setDraggingCaseId(null)
    },
  })

  const runApiCaseMutation = useMutation({
    mutationFn: ({ caseId, environmentId }: { caseId: string; environmentId: string }) => api.runApiCase(caseId, { environmentId }),
    onSuccess: (result) => {
      setRunResult(result)
      setRunResultView('response')
      previousApiCaseRunStatusRef.current = result.status ?? ''
      const resultRunId = getApiCaseRunId(result)

      if (resultRunId && isApiRunPollingStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        message.info('已开始运行用例')
        return
      }

      if (resultRunId && !isApiRunTerminalStatus(result.status)) {
        setActiveApiCaseRunId(resultRunId)
        message.info('已创建运行记录，正在等待结果')
        return
      }

      if (isApiRunPollingStatus(result.status)) {
        message.error('已创建运行记录，但未获取到运行 ID')
        return
      }

      setActiveApiCaseRunId('')
      if (result.status === 'success' || result.success) {
        message.success('运行完成')
        return
      }
      if (result.status === 'failed') {
        message.error(result.errorMessage || '运行完成，断言失败')
        return
      }
      message.error(result.errorMessage || '运行异常')
    },
    onSettled: (_result, _error, variables) => {
      if (!variables?.environmentId) return
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', variables.environmentId] })
    },
    onError: () => {
      setRunResult(null)
      setActiveApiCaseRunId('')
      previousApiCaseRunStatusRef.current = ''
    },
  })

  const runApiCollectionMutation = useMutation({
    mutationFn: ({ collectionId: targetCollectionId, environmentId }: { collectionId: string; environmentId: string }) =>
      api.runApiCollection(targetCollectionId, { environmentId }),
    onSuccess: (summary) => {
      if (!summary.collectionRunId) {
        message.error('未获取到运行记录 ID')
        return
      }

      previousActiveRunStatusRef.current = summary.status ?? ''
      setActivePollingCollectionRunId(summary.collectionRunId)
      setCollectionRunHistoryOpen(true)
      queryClient.setQueryData<ApiCollectionRunSummary[]>(['apiCollectionRuns', collectionId], (current) => {
        const currentItems = current ?? []
        return [summary, ...currentItems.filter((item) => item.collectionRunId !== summary.collectionRunId)]
      })
      message.success(isApiRunPollingStatus(summary.status) ? '已开始运行测试' : '已创建运行记录')
    },
    onSettled: (_result, _error, variables) => {
      if (!variables?.environmentId) return
      queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', variables.environmentId] })
      queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
    },
  })

  const importApiCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) => api.importApiCases(collectionId, file, filename),
    onSuccess: (result) => {
      message.success(
        `导入成功：${result.importedCaseCount ?? 0} 条用例，${result.importedExtractRuleCount ?? 0} 条提取规则，${result.importedAssertRuleCount ?? 0} 条断言规则`,
      )
      setCaseImportModalOpen(false)
      setCaseImportMode('upload')
      setImportYamlFile(null)
      setImportYamlText('')
      queryClient.invalidateQueries({ queryKey: ['apiCases', collectionId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const saveAssertRuleMutation = useMutation({
    mutationFn: (values: AssertRuleFormValues) => {
      if (!activeCaseId) throw new Error('请先保存用例')
      if (editingAssertRule) {
        return api.updateApiAssertRule(
          normalizeAssertRuleId(editingAssertRule),
          buildApiAssertRuleUpdatePayload(editingAssertRule, values),
        )
      }
      return api.createApiAssertRule(activeCaseId, values)
    },
    onSuccess: () => {
      message.success(editingAssertRule ? '断言规则已更新' : '断言规则已创建')
      setAssertRuleModalOpen(false)
      setEditingAssertRule(null)
      assertRuleForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const deleteAssertRuleMutation = useMutation({
    mutationFn: (assertRuleId: string) => api.deleteApiAssertRule(assertRuleId),
    onSuccess: () => {
      message.success('断言规则已删除')
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const toggleAssertRuleMutation = useMutation({
    mutationFn: ({ assertRuleId, enabled }: { assertRuleId: string; enabled: boolean }) => api.updateApiAssertRule(assertRuleId, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiAssertRules', activeCaseId] })
    },
  })

  const saveExtractRuleMutation = useMutation({
    mutationFn: (values: ExtractRuleFormValues) => {
      if (!activeCaseId) throw new Error('请先保存用例')
      if (editingExtractRule) {
        return api.updateApiExtractRule(
          normalizeExtractRuleId(editingExtractRule),
          buildApiExtractRuleUpdatePayload(editingExtractRule, values),
        )
      }
      return api.createApiExtractRule(activeCaseId, values)
    },
    onSuccess: () => {
      message.success(editingExtractRule ? '提取规则已更新' : '提取规则已创建')
      setExtractRuleModalOpen(false)
      setEditingExtractRule(null)
      extractRuleForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  const deleteExtractRuleMutation = useMutation({
    mutationFn: (extractRuleId: string) => api.deleteApiExtractRule(extractRuleId),
    onSuccess: () => {
      message.success('提取规则已删除')
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  const toggleExtractRuleMutation = useMutation({
    mutationFn: ({ extractRuleId, enabled }: { extractRuleId: string; enabled: boolean }) => api.updateApiExtractRule(extractRuleId, { enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['apiExtractRules', activeCaseId] })
    },
  })

  const switchDefaultEnvironmentMutation = useMutation({
    mutationFn: async (nextEnvironmentId: string) => {
      const nextEnvironment = environments.find((environment) => normalizeEnvironmentId(environment) === nextEnvironmentId)
      if (!nextEnvironment) throw new Error('未找到所选环境')

      const currentDefaultEnvironment = environments.find((environment) => environment.isDefault)
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
      queryClient.invalidateQueries({ queryKey: ['apiEnvironments', projectId] })
    },
  })

  async function handleSendRequest() {
    try {
      if (!resolvedEnvironmentId) {
        message.warning('请先选择可用环境')
        return
      }

      if (isCreatingCase) {
        message.warning('请先保存用例后再发送')
        return
      }

      if (!editingCase || getCaseId(editingCase) !== activeCaseId) {
        message.warning('用例详情加载中，请稍后再试')
        return
      }

      await caseForm.validateFields()
      const values = getCompleteCaseFormValues()
      const payload = buildApiCaseUpdatePayload(editingCase, values)

      if (Object.keys(payload).length > 0) {
        message.warning('当前有未保存修改，请先保存后再发送')
        return
      }

      await runApiCaseMutation.mutateAsync({ caseId: activeCaseId, environmentId: resolvedEnvironmentId })
    } catch (error) {
      if (error instanceof Error) {
        message.error(getErrorMessage(error))
      }
      // validation errors are shown by the form
    }
  }

  async function handleRunCollection() {
    if (!collectionId) return
    if (!resolvedEnvironmentId) {
      message.warning('请先选择可用环境')
      return
    }
    if (cases.length === 0) {
      message.warning('当前 Collection 还没有可运行的用例')
      return
    }

    try {
      await runApiCollectionMutation.mutateAsync({ collectionId, environmentId: resolvedEnvironmentId })
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  async function handleRefreshCollectionRunReport() {
    const collectionRunId = selectedCollectionRunId
    if (!collectionRunId) return

    setRefreshingCollectionRunReport(true)
    try {
      await collectionRunReportQuery.refetch()
      await queryClient.invalidateQueries({ queryKey: ['apiCollectionRun', collectionRunId] })
      await queryClient.invalidateQueries({ queryKey: ['apiCollectionRuns', collectionId] })
      message.success('报告已刷新')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setRefreshingCollectionRunReport(false)
    }
  }

  function handleExportCollectionRunReportHtml() {
    if (!collectionRunReport) return

    const environmentName =
      environments.find((environment) => normalizeEnvironmentId(environment) === collectionRunReport.environmentId)?.name ??
      collectionRunReport.environmentId ??
      '-'
    const collectionName = collectionQuery.data?.name || 'API测试集'
    const html = buildCollectionRunReportHtml({
      collectionName,
      environmentName,
      report: collectionRunReport,
      items: orderedCollectionRunItems,
    })
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const startedAtText = collectionRunReport.startedAt ? formatTime(collectionRunReport.startedAt).replaceAll(/[/: ]/g, '-') : 'report'
    link.href = objectUrl
    link.download = `${sanitizeFileName(collectionName)}-${sanitizeFileName(startedAtText)}.html`
    document.body.append(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(objectUrl)
    message.success('HTML 报告已导出')
  }

  function handleOpenCollectionRunHistoryItem(historyItem: ApiCollectionRunSummary) {
    setLoadingCollectionRunHistoryId(historyItem.collectionRunId ?? '')
    setSelectedCollectionRunId(historyItem.collectionRunId ?? '')
    setCollectionRunReportOpen(true)
    if (isApiRunPollingStatus(historyItem.status) && historyItem.collectionRunId) {
      previousActiveRunStatusRef.current = historyItem.status
      setActivePollingCollectionRunId(historyItem.collectionRunId)
    }
    setCollectionRunHistoryOpen(false)
  }

  function toggleCollectionRunItem(itemKey: string) {
    setExpandedCollectionRunItemIds((current) => (current.includes(itemKey) ? current.filter((key) => key !== itemKey) : [...current, itemKey]))
  }

  function handleCollectionRunItemViewChange(itemKey: string, view: RunResultView) {
    setCollectionRunItemViews((current) => (current[itemKey] === view ? current : { ...current, [itemKey]: view }))
  }

  function renderRunResultContent(params: {
    view: RunResultView
    request?: ApiCaseRunResult['request']
    response?: ApiCaseRunResult['response']
    extractResults?: ApiCaseRunResult['extractResults']
    assertResults?: ApiCaseRunResult['assertResults']
    emptyExtractDescription?: string
    emptyAssertDescription?: string
  }): ReactNode {
    const {
      view,
      request,
      response,
      extractResults: currentExtractResults = [],
      assertResults: currentAssertResults = [],
      emptyExtractDescription = '暂无提取结果',
      emptyAssertDescription = '暂无断言结果',
    } = params

    if (view === 'request') {
      const hasRequestSnapshot = Boolean(request?.url || request?.method || request?.bodyType || request?.headersJson || request?.queryJson || request?.body)
      if (!hasRequestSnapshot) {
        return <Empty description="请求快照尚未生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      }

      return (
        <pre className="api-case-run-result-pre compact">
{JSON.stringify(
  {
    url: request?.url,
    method: request?.method,
    bodyType: request?.bodyType,
    headers: parseMaybeJsonValue(request?.headersJson),
    query: parseMaybeJsonValue(request?.queryJson),
    body: parseMaybeJsonValue(request?.body),
  },
  null,
  2,
)}
        </pre>
      )
    }

    if (view === 'response') {
      const hasResponseSnapshot = Boolean(response?.statusCode || response?.headersJson || response?.body)
      if (!hasResponseSnapshot) {
        return <Empty description="响应结果尚未生成" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      }

      return (
        <pre className="api-case-run-result-pre compact">
{JSON.stringify(parseMaybeJsonValue(response?.body), null, 2)}
        </pre>
      )
    }

    if (view === 'extract') {
      return (
        <div className="api-case-run-result-subsection">
          {currentExtractResults.length === 0 ? (
            <Empty description={emptyExtractDescription} image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div className="api-case-run-result-list">
              {currentExtractResults.map((item, index) => (
                <div key={`${item.extractRuleId ?? index}`} className={`api-case-run-result-row${item.success ? '' : ' failed'}`}>
                  <div className="api-case-run-result-row-title">
                    <strong>{item.name ?? `提取 ${index + 1}`}</strong>
                    <Tag color={item.success ? 'success' : 'error'}>{item.success ? '成功' : '失败'}</Tag>
                    {item.usedDefault ? <Tag color="gold">默认值</Tag> : null}
                  </div>
                  <div className="api-case-run-result-row-meta">
                    <span className="api-case-run-result-meta-item">
                      <strong>变量</strong>
                      <span>{formatOptionalValue(item.varKey)}</span>
                    </span>
                    <span className="api-case-run-result-meta-item">
                      <strong>值</strong>
                      <span>{formatOptionalValue(item.value)}</span>
                    </span>
                    <span className="api-case-run-result-meta-item">
                      <strong>信息</strong>
                      <span>{formatOptionalValue(item.errorMessage)}</span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    return (
      <div className="api-case-run-result-subsection">
        {currentAssertResults.length === 0 ? (
          <Empty description={emptyAssertDescription} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <div className="api-case-run-result-list">
            {currentAssertResults.map((item, index) => (
              <div key={`${item.assertRuleId ?? index}`} className={`api-case-run-result-row${item.success ? '' : ' failed'}`}>
                <div className="api-case-run-result-row-title">
                  <strong>{item.name ?? `断言 ${index + 1}`}</strong>
                  <Tag color={item.success ? 'success' : 'error'}>{item.success ? '成功' : '失败'}</Tag>
                </div>
                <div className="api-case-run-result-row-meta">
                  <span className="api-case-run-result-meta-item">
                    <strong>来源</strong>
                    <span>{assertSourceLabelMap[item.assertSource as ApiAssertSource] ?? formatOptionalValue(item.assertSource)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>比较</strong>
                    <span>{assertComparatorLabelMap[item.comparator as ApiAssertComparator] ?? formatOptionalValue(item.comparator)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>目标</strong>
                    <span>{formatOptionalValue(item.targetExpr)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>期望</strong>
                    <span>{formatOptionalValue(item.expectedValue)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>实际</strong>
                    <span>{formatOptionalValue(item.actualValue)}</span>
                  </span>
                  <span className="api-case-run-result-meta-item">
                    <strong>信息</strong>
                    <span>{formatOptionalValue(item.errorMessage)}</span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  const ensureTrailingRow = useCallback((field: 'query' | 'headers', items?: Array<{ enabled?: boolean; key?: string; value?: string }>) => {
    const rows = items ?? []
    if (rows.length === 0) {
      caseForm.setFieldValue(field, [{ enabled: false, key: '', value: '' }])
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
      caseForm.setFieldValue(field, [...nextRows, { enabled: false, key: '', value: '' }])
      return
    }

    const changed = JSON.stringify(rows) !== JSON.stringify(nextRows)
    if (changed) caseForm.setFieldValue(field, nextRows)
  }, [caseForm])

  useEffect(() => {
    ensureTrailingRow('query', watchedQuery)
  }, [ensureTrailingRow, watchedQuery])

  useEffect(() => {
    ensureTrailingRow('headers', watchedHeaders)
  }, [ensureTrailingRow, watchedHeaders])

  useEffect(() => {
    setRunResult(null)
    setRunResultView('response')
    setAssertRuleModalOpen(false)
    setExtractRuleModalOpen(false)
    setEditingAssertRule(null)
    setEditingExtractRule(null)
    assertRuleForm.resetFields()
    extractRuleForm.resetFields()
  }, [assertRuleForm, extractRuleForm, selectedCaseId])

  useEffect(() => {
    if (selectedCaseId !== DRAFT_CASE_ID) return

    setEditingCase(null)
    caseForm.setFieldsValue(draftCaseValues ?? createDefaultCaseFormValues())
  }, [caseForm, draftCaseValues, selectedCaseId])

  useEffect(() => {
    if (!activeCaseId || !selectedCaseDetailQuery.data) return

    setEditingCase(selectedCaseDetailQuery.data)
    caseForm.setFieldsValue(buildCaseFormValues(selectedCaseDetailQuery.data))
  }, [activeCaseId, caseForm, selectedCaseDetailQuery.data])

  useEffect(() => {
    if (!runResult || !isResizingEditor) return

    function handlePointerMove(event: PointerEvent) {
      const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
      const dragState = editorResizeRef.current
      if (!dragState || containerHeight === 0) return

      const delta = event.clientY - dragState.startY
      const maxHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, containerHeight - MIN_EDITOR_RESULT_HEIGHT - 18)
      const nextHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, Math.min(maxHeight, dragState.startHeight + delta))
      setEditorTopHeight(nextHeight)
    }

    function handlePointerUp() {
      setIsResizingEditor(false)
      editorResizeRef.current = null
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [isResizingEditor, runResult])

  useEffect(() => {
    if (!runResult) return

    function syncEditorTopHeight() {
      const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
      if (containerHeight === 0) return

      const maxHeight = Math.max(MIN_EDITOR_TOP_HEIGHT, containerHeight - MIN_EDITOR_RESULT_HEIGHT - 18)
      setEditorTopHeight((current) => Math.max(MIN_EDITOR_TOP_HEIGHT, Math.min(maxHeight, current)))
    }

    syncEditorTopHeight()
    window.addEventListener('resize', syncEditorTopHeight)

    return () => {
      window.removeEventListener('resize', syncEditorTopHeight)
    }
  }, [runResult])

  function handleEditorSplitterPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
    if (containerHeight === 0) return

    editorResizeRef.current = {
      startY: event.clientY,
      startHeight: editorTopHeight,
    }
    setIsResizingEditor(true)
    event.currentTarget.setPointerCapture(event.pointerId)
    event.preventDefault()
  }

  function formatEnvironmentToken(varKey: string) {
    return `${ENV_VAR_TOKEN_PREFIX}${varKey}${ENV_VAR_TOKEN_SUFFIX}`
  }

  function setEnvVarInputRef(fieldKey: string, ref: InputRef | null) {
    if (!ref) {
      delete envVarInputRefs.current[fieldKey]
      return
    }
    envVarInputRefs.current[fieldKey] = ref
  }

  function openEnvVarPicker(fieldKey: string) {
    const defaultMode: EnvVarPickerMode = resolvedEnvironmentId ? 'environment' : 'builtin'
    setEnvVarPickerOpenKey(fieldKey)
    setEnvVarPickerMode(defaultMode)
    setEnvVarPickerSearch('')
    setEnvVarPickerSelectedKey(
      defaultMode === 'environment' ? formatEnvironmentToken(environmentVars[0]?.varKey ?? '') : builtinTemplateFunctions[0]?.token ?? '',
    )
  }

  function closeEnvVarPicker() {
    setEnvVarPickerOpenKey(null)
    setEnvVarPickerMode('environment')
    setEnvVarPickerSearch('')
    setEnvVarPickerSelectedKey('')
  }

  function insertTemplateText(fieldPath: Array<string | number>, fieldKey: string, templateText: string) {
    const currentValue = String(caseForm.getFieldValue(fieldPath as never) ?? '')
    const inputRef = envVarInputRefs.current[fieldKey]
    const inputElement = inputRef?.input ?? null

    if (inputElement) {
      const selectionStart = inputElement.selectionStart ?? currentValue.length
      const selectionEnd = inputElement.selectionEnd ?? selectionStart
      const nextValue = `${currentValue.slice(0, selectionStart)}${templateText}${currentValue.slice(selectionEnd)}`
      caseForm.setFieldValue(fieldPath as never, nextValue)

      requestAnimationFrame(() => {
        inputElement.focus()
        const caretPosition = selectionStart + templateText.length
        inputElement.setSelectionRange?.(caretPosition, caretPosition)
      })
    } else {
      caseForm.setFieldValue(fieldPath as never, `${currentValue}${templateText}`)
    }

    closeEnvVarPicker()
  }

  function insertTemplateTextIntoJson(templateText: string) {
    bodyJsonEditorRef.current?.insertText(templateText)
    closeEnvVarPicker()
  }

  function handleFormatBodyJson() {
    bodyJsonEditorRef.current?.formatDocument()
  }

  function renderEnvVarPicker({
    pickerKey,
    onInsert,
    trigger,
  }: {
    pickerKey: string
    onInsert: (templateText: string) => void
    trigger: ReactNode
    placement?: 'bottomRight' | 'bottomLeft'
  }) {
    envVarPickerInsertHandlersRef.current[pickerKey] = onInsert

    return (
      <span
        className="api-env-var-picker-trigger-wrap"
        onClick={(event) => {
          event.preventDefault()
          event.stopPropagation()
          openEnvVarPicker(pickerKey)
        }}
      >
        {trigger}
      </span>
    )
  }

  function renderEnvVarPickerModal() {
    const hasEnvironment = Boolean(resolvedEnvironmentId)
    const isBuiltinMode = envVarPickerMode === 'builtin'
    const pickerItems = isBuiltinMode
      ? filteredBuiltinTemplateFunctions.map((item) => ({
          key: item.token,
          title: item.label,
          description: item.description,
          type: '内置函数',
          example: item.example,
        }))
      : filteredEnvironmentVars.map((item) => ({
          key: formatEnvironmentToken(item.varKey),
          title: item.varKey,
          description: item.description?.trim() || '',
          type: '环境变量',
          example: '',
        }))
    const handleInsert = envVarPickerOpenKey ? envVarPickerInsertHandlersRef.current[envVarPickerOpenKey] : undefined
    const selectedItem = pickerItems.find((item) => item.key === envVarPickerSelectedKey)
    const selectPickerMode = (nextMode: EnvVarPickerMode) => {
      setEnvVarPickerMode(nextMode)
      setEnvVarPickerSearch('')
      setEnvVarPickerSelectedKey(
        nextMode === 'builtin'
          ? builtinTemplateFunctions[0]?.token ?? ''
          : formatEnvironmentToken(environmentVars[0]?.varKey ?? ''),
      )
    }

    return (
      <Modal
        mask={{ closable: false }}
        open={Boolean(envVarPickerOpenKey)}
        title={(
          <div className="api-env-var-picker-heading">
            <div className="api-env-var-picker-heading-title">插入动态值</div>
            <div className="api-env-var-picker-heading-subtitle">从环境变量或内置函数中选择一个值，自动插入到当前输入框</div>
          </div>
        )}
        footer={null}
        centered
        width={880}
        destroyOnHidden={false}
        className="api-env-var-picker-modal"
        onCancel={closeEnvVarPicker}
      >
        <div className="api-env-var-picker api-env-var-picker-modal-body">
          <div className="api-env-var-picker-workspace">
            <nav className="api-env-var-picker-sources" aria-label="动态值来源">
              <button
                type="button"
                className={`api-env-var-picker-source${envVarPickerMode === 'environment' ? ' active' : ''}`}
                onClick={() => selectPickerMode('environment')}
              >
                <CodeSandboxOutlined />
                <span>环境变量</span>
                <span className="api-env-var-picker-source-count">{environmentVars.length}</span>
              </button>
              <button
                type="button"
                className={`api-env-var-picker-source${envVarPickerMode === 'builtin' ? ' active' : ''}`}
                onClick={() => selectPickerMode('builtin')}
              >
                <FunctionOutlined />
                <span>内置函数</span>
                <span className="api-env-var-picker-source-count">{builtinTemplateFunctions.length}</span>
              </button>
            </nav>

            <section className="api-env-var-picker-browser">
              <Input
                allowClear
                prefix={<SearchOutlined />}
                className="api-env-var-picker-search"
                placeholder={isBuiltinMode ? '搜索函数名或表达式' : '搜索变量名'}
                value={envVarPickerSearch}
                onChange={(event) => setEnvVarPickerSearch(event.target.value)}
                disabled={!isBuiltinMode && !hasEnvironment}
              />
              <div className="api-env-var-picker-list">
                {!isBuiltinMode && !hasEnvironment ? (
                  <div className="api-env-var-picker-empty">请先选择环境</div>
                ) : !isBuiltinMode && environmentVarsQuery.isLoading ? (
                  <div className="api-env-var-picker-empty">环境变量加载中...</div>
                ) : pickerItems.length === 0 ? (
                  <div className="api-env-var-picker-empty">{isBuiltinMode ? '没有匹配的内置函数' : '没有匹配的环境变量'}</div>
                ) : (
                  pickerItems.map((item) => {
                    const active = item.key === envVarPickerSelectedKey
                    return (
                      <button
                        key={item.key}
                        type="button"
                        className={`api-env-var-picker-item${active ? ' active' : ''}`}
                        onClick={() => setEnvVarPickerSelectedKey(item.key)}
                        onDoubleClick={() => handleInsert?.(item.key)}
                      >
                        <span className="api-env-var-picker-item-status" />
                        <span className="api-env-var-picker-item-main">
                          <span className="api-env-var-picker-item-key">{item.title}</span>
                          {item.description ? <span className="api-env-var-picker-item-desc">{item.description}</span> : null}
                          {isBuiltinMode && item.example ? <code className="api-env-var-picker-item-example">{item.example}</code> : null}
                        </span>
                        <span className="api-env-var-picker-item-type">{item.type}</span>
                        {active ? <CheckOutlined className="api-env-var-picker-item-check" /> : null}
                      </button>
                    )
                  })
                )}
              </div>
            </section>

            <aside className="api-env-var-picker-preview">
              <div className="api-env-var-picker-preview-title">插入预览</div>
              <code className="api-env-var-picker-preview-token">{selectedItem?.key || '请选择动态值'}</code>
              <dl className="api-env-var-picker-preview-meta">
                <div>
                  <dt>来源</dt>
                  <dd>{isBuiltinMode ? '内置函数' : '当前环境'}</dd>
                </div>
                <div>
                  <dt>{isBuiltinMode ? '函数名' : '变量名'}</dt>
                  <dd>{selectedItem?.title || '-'}</dd>
                </div>
              </dl>
              <p className="api-env-var-picker-preview-description">
                {selectedItem?.description || (isBuiltinMode
                  ? '插入后将在运行时由后端生成对应值。'
                  : '将以上内容插入当前输入框后，运行时会自动替换为对应的环境变量值。')}
              </p>
            </aside>
          </div>

          <div className="api-env-var-picker-footer">
            <Button onClick={closeEnvVarPicker}>取消</Button>
            <Button
              type="primary"
              className="api-env-var-picker-insert-btn"
              disabled={!envVarPickerSelectedKey || !handleInsert}
              onClick={() => handleInsert?.(envVarPickerSelectedKey)}
            >
              插入变量
            </Button>
          </div>
        </div>
      </Modal>
    )
  }

  const resetCaseForm = useCallback(() => {
    caseForm.setFieldsValue(createDefaultCaseFormValues())
  }, [caseForm])

  function openCreateDrawer() {
    const nextDraft = draftCaseValues ?? createDefaultCaseFormValues()
    setDraftCaseValues(nextDraft)
    setSelectedCaseId(DRAFT_CASE_ID)
    setEditingCase(null)
    caseForm.setFieldsValue(nextDraft)
  }

  function openCaseImportModal() {
    setCaseImportModalOpen(true)
  }

  function closeCaseImportModal() {
    if (importApiCasesMutation.isPending) return
    setCaseImportModalOpen(false)
    setCaseImportMode('upload')
    setImportYamlFile(null)
    setImportYamlText('')
  }

  function handleImportApiCases() {
    if (!collectionId) return

    if (caseImportMode === 'upload') {
      if (!importYamlFile) {
        message.warning('请上传 YAML 文件')
        return
      }
      if (!isYamlFileName(importYamlFile.name)) {
        message.warning('仅支持 .yaml 或 .yml 文件')
        return
      }

      importApiCasesMutation.mutate({
        file: importYamlFile,
        filename: importYamlFile.name,
      })
      return
    }

    const yamlContent = importYamlText.trim()
    if (!yamlContent) {
      message.warning('请输入 YAML 内容')
      return
    }

    const generatedFileName = `collection-${collectionId || 'cases'}.yaml`
    importApiCasesMutation.mutate({
      file: new File([yamlContent], generatedFileName, { type: 'application/x-yaml' }),
      filename: generatedFileName,
    })
  }

  function handleSelectEnvironment(nextEnvironmentId: string) {
    if (!nextEnvironmentId || nextEnvironmentId === resolvedEnvironmentId) {
      setEnvironmentPopoverOpen(false)
      return
    }

    switchDefaultEnvironmentMutation.mutate(nextEnvironmentId)
  }

  function openCreateAssertRule() {
    if (!activeCaseId) {
      message.warning('请先保存用例')
      return
    }

    setEditingAssertRule(null)
    setAssertRuleModalOpen(true)
    assertRuleForm.setFieldsValue({
      name: '',
      enabled: true,
      orderNo: assertRules.length + 1,
      assertSource: 'status_code',
      targetExpr: '',
      comparator: 'eq',
      expectedValue: '',
    })
  }

  function openEditAssertRule(rule: ApiAssertRule) {
    setEditingAssertRule(rule)
    setAssertRuleModalOpen(true)
    assertRuleForm.setFieldsValue({
      name: rule.name,
      enabled: rule.enabled,
      orderNo: rule.orderNo,
      assertSource: rule.assertSource,
      targetExpr: rule.targetExpr,
      comparator: rule.comparator,
      expectedValue: rule.expectedValue,
    })
  }

  function openCreateExtractRule() {
    if (!activeCaseId) {
      message.warning('请先保存用例')
      return
    }

    setEditingExtractRule(null)
    setExtractRuleModalOpen(true)
    extractRuleForm.setFieldsValue({
      name: '',
      enabled: true,
      orderNo: extractRules.length + 1,
      source: 'body_jsonpath',
      sourceExpr: '',
      varKey: '',
      defaultValue: '',
    })
  }

  function openEditExtractRule(rule: ApiExtractRule) {
    setEditingExtractRule(rule)
    setExtractRuleModalOpen(true)
    extractRuleForm.setFieldsValue({
      name: rule.name,
      enabled: rule.enabled,
      orderNo: rule.orderNo,
      source: rule.source,
      sourceExpr: rule.sourceExpr,
      varKey: rule.varKey,
      defaultValue: rule.defaultValue,
    })
  }

  const cases = casesQuery.data ?? EMPTY_API_CASES
  const collectionRunHistory = useMemo(
    () =>
      [...listItems(collectionRunHistoryQuery.data)].sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [collectionRunHistoryQuery.data],
  )
  const collectionRunReport = collectionRunReportQuery.data ?? null
  const selectedCollectionRunSummary =
    (selectedCollectionRunId && activeCollectionRunQuery.data?.collectionRunId === selectedCollectionRunId ? activeCollectionRunQuery.data : undefined) ??
    collectionRunHistory.find((item) => item.collectionRunId === selectedCollectionRunId)
  const assertRulesQuery = useQuery({
    queryKey: ['apiAssertRules', activeCaseId],
    queryFn: () => api.getApiAssertRules(activeCaseId),
    enabled: Boolean(activeCaseId),
  })
  const extractRulesQuery = useQuery({
    queryKey: ['apiExtractRules', activeCaseId],
    queryFn: () => api.getApiExtractRules(activeCaseId),
    enabled: Boolean(activeCaseId),
  })
  const assertRules = useMemo(() => sortRulesByOrderNo(assertRulesQuery.data ?? EMPTY_ASSERT_RULES), [assertRulesQuery.data])
  const extractRules = useMemo(() => sortRulesByOrderNo(extractRulesQuery.data ?? EMPTY_EXTRACT_RULES), [extractRulesQuery.data])
  const extractResults = runResult?.extractResults ?? []
  const assertResults = runResult?.assertResults ?? []
  const runResultStatus = runResult?.status ?? (runResult ? (runResult.success ? 'success' : 'failed') : undefined)
  const runResultStatusMeta = getExecutionStatusMeta(runResultStatus)
  const isApiCaseRunInProgress = isApiRunPollingStatus(runResultStatus)
  const failedExtractCount = extractResults.filter((item) => !item.success).length
  const failedAssertCount = assertResults.filter((item) => !item.success).length
  const postOperationCount = assertRules.length + extractRules.length
  const orderedCollectionRunItems = useMemo(
    () =>
      [...(collectionRunReport?.items ?? [])].sort((left, right) => {
        const leftOrderNo = left.orderNo ?? Number.MAX_SAFE_INTEGER
        const rightOrderNo = right.orderNo ?? Number.MAX_SAFE_INTEGER
        if (leftOrderNo !== rightOrderNo) return leftOrderNo - rightOrderNo
        return (left.caseName ?? '').localeCompare(right.caseName ?? '')
      }),
    [collectionRunReport?.items],
  )

  const filteredCases = useMemo(() => {
    const keyword = caseSearch.trim().toLowerCase()
    if (!keyword) return cases

    return cases.filter((item) =>
      [item.name, item.urlTemplate, item.description, item.method]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keyword)),
    )
  }, [caseSearch, cases])

  const orderedByRuleCases = useMemo(() => sortCasesByOrderNo(filteredCases), [filteredCases])

  const draftCase = useMemo<ApiCase | null>(
    () =>
      draftCaseValues
        ? {
            caseId: DRAFT_CASE_ID,
            name: draftCaseValues.name?.trim() || '未保存用例',
            description: draftCaseValues.description,
            method: draftCaseValues.method || 'POST',
            urlTemplate: draftCaseValues.path?.trim() || '/v1/example',
            enabled: draftCaseValues.enabled,
          }
        : null,
    [draftCaseValues],
  )

  useEffect(() => {
    if (reorderCasesMutation.isPending) return

    const nextIds = sortCasesByOrderNo(cases)
      .map((item) => getCaseId(item))
      .filter(Boolean)

    setCaseOrderIds((current) => {
      if (nextIds.length === 0) return current.length === 0 ? current : []
      if (current.length === 0) return nextIds

      const currentFiltered = current.filter((id) => nextIds.includes(id))
      if (currentFiltered.length === nextIds.length && currentFiltered.every((id, index) => id === nextIds[index])) {
        return currentFiltered
      }

      return nextIds
    })
  }, [cases, reorderCasesMutation.isPending])

  const orderedCases = useMemo(() => {
    if (caseOrderIds.length === 0) return orderedByRuleCases

    const caseMap = new Map(orderedByRuleCases.map((item) => [getCaseId(item), item]))
    const ordered = caseOrderIds.map((caseId) => caseMap.get(caseId)).filter(Boolean) as ApiCase[]
    const missing = orderedByRuleCases.filter((item) => !caseOrderIds.includes(getCaseId(item)))
    return [...ordered, ...missing]
  }, [caseOrderIds, orderedByRuleCases])

  const sidebarCases = useMemo(() => (draftCase ? [draftCase, ...orderedCases] : orderedCases), [draftCase, orderedCases])
  const selectedCasePreview = useMemo(
    () => orderedCases.find((item) => getCaseId(item) === activeCaseId) ?? cases.find((item) => getCaseId(item) === activeCaseId) ?? null,
    [activeCaseId, cases, orderedCases],
  )

  const canReorder = can('write') && caseSearch.trim().length === 0

  useEffect(() => {
    if (!activeCaseId || selectedCaseId === DRAFT_CASE_ID) return
    if (editingCase && getCaseId(editingCase) === activeCaseId) return
    if (!selectedCasePreview) return

    setEditingCase(selectedCasePreview)
    caseForm.setFieldsValue(buildCaseFormValues(selectedCasePreview))
  }, [activeCaseId, caseForm, editingCase, selectedCaseId, selectedCasePreview])

  useEffect(() => {
    if (sidebarCases.length === 0) {
      if (selectedCaseId) {
        setSelectedCaseId('')
        setEditingCase(null)
        resetCaseForm()
      }
      return
    }

    const exists = sidebarCases.some((item) => getCaseId(item) === selectedCaseId)
    if (!selectedCaseId || !exists) {
      const fallbackCase = sidebarCases[0]
      const fallbackId = getCaseId(fallbackCase)
      setSelectedCaseId(fallbackId)
    }
  }, [resetCaseForm, selectedCaseId, sidebarCases])

  function handleCaseDragStart(event: DragEvent<HTMLDivElement>, caseId: string) {
    if (!canReorder || caseId === DRAFT_CASE_ID) return
    setDraggingCaseId(caseId)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', caseId)
  }

  function handleCaseDrop(targetCaseId: string) {
    if (!draggingCaseId || draggingCaseId === targetCaseId || !canReorder) return
    if (draggingCaseId === DRAFT_CASE_ID || targetCaseId === DRAFT_CASE_ID) return

    const baseOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : orderedCases.map((item) => getCaseId(item)).filter(Boolean)).filter(
      (caseId) => caseId !== DRAFT_CASE_ID,
    )
    const fromIndex = baseOrderIds.indexOf(draggingCaseId)
    const toIndex = baseOrderIds.indexOf(targetCaseId)
    if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return

    const nextOrderIds = moveArrayItem(baseOrderIds, fromIndex, toIndex)
    caseOrderRollbackRef.current = caseOrderIds
    setCaseOrderIds(nextOrderIds)
    reorderCasesMutation.mutate(nextOrderIds)
  }

  return (<ProjectAccessScope projectId={projectId ?? ''}>{(
    <div className="workbench-page api-collection-detail-page">
      <div className="api-automation-content">
        <div className="page-frame api-collection-detail-frame">
          <div className="api-collection-detail-layout">
            {collectionQuery.error ? <Alert showIcon type="error" title={getErrorMessage(collectionQuery.error)} /> : null}
            {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}
            {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getErrorMessage(selectedCaseDetailQuery.error)} /> : null}
            {requirementQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementQuery.error)} /> : null}
            {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
            {assertRulesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(assertRulesQuery.error)} /> : null}
            {extractRulesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(extractRulesQuery.error)} /> : null}

            <aside className="workbench-panel api-case-sidebar">
              <div className="panel-header api-case-sidebar-header">
                <div className="api-case-sidebar-title">
                  <Button
                    type="text"
                    icon={<ArrowLeftOutlined />}
                    className="api-case-back-button"
                    onClick={() => navigate('/api-automation')}
                    aria-label="返回 Collection 列表"
                  />
                </div>
                <div className="api-case-sidebar-meta">
                  <Text type="secondary" className="api-case-sidebar-count">
                    {sidebarCases.length} 个用例
                  </Text>
                  <ProjectActionButton action="write"
                    type="primary"
                    className="action-btn-create"
                    shape="circle"
                    operation="create" iconOnly
                    onClick={openCreateDrawer}
                    aria-label="新建用例"
                  />
                </div>
              </div>

              <div className="api-case-sidebar-toolbar">
                <Input
                  allowClear
                  value={caseSearch}
                  prefix={<SearchOutlined />}
                  placeholder="搜索用例名称 / 路径"
                  onChange={(event) => setCaseSearch(event.target.value)}
                />
                <ProjectActionButton action="execute" className="api-case-import-trigger" operation="upload" onClick={openCaseImportModal}>
                  用例导入
                </ProjectActionButton>
              </div>

              <div className="api-case-sidebar-scroll">
                {casesQuery.isLoading ? (
                  <div className="sprint-card-loading">
                    <Empty description="用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                ) : sidebarCases.length === 0 ? (
                  <div className="sprint-card-loading">
                    <Empty description={cases.length === 0 ? '当前还没有用例' : '没有匹配到用例'}>
                      <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateDrawer}>
                        新建用例
                      </ProjectActionButton>
                    </Empty>
                  </div>
                ) : (
                  <div className="api-case-nav-list">
                    {sidebarCases.map((item) => {
                      const caseId = getCaseId(item)
                      const selected = caseId === selectedCaseId

                      return (
                        <div
                          key={caseId}
                          className={`api-case-nav-item${selected ? ' selected' : ''}${draggingCaseId === caseId ? ' dragging' : ''}${canReorder ? ' can-drag' : ''}`}
                          role="button"
                          tabIndex={0}
                          draggable={canReorder && caseId !== DRAFT_CASE_ID}
                          onDragStart={(event) => handleCaseDragStart(event, caseId)}
                          onDragOver={(event) => {
                            if (!canReorder || caseId === DRAFT_CASE_ID) return
                            event.preventDefault()
                          }}
                          onDrop={(event) => {
                            event.preventDefault()
                            handleCaseDrop(caseId)
                          }}
                          onDragEnd={() => {
                            setDraggingCaseId(null)
                          }}
                          onClick={() => {
                            setSelectedCaseId(caseId)
                          }}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              setSelectedCaseId(caseId)
                            }
                          }}
                        >
                          <div className="api-case-nav-item-main">
                            <div className="api-case-nav-item-tags">
                              <Tag className="api-case-table-method" color={methodTagColor(item.method)}>
                                {item.method}
                              </Tag>
                              {caseId === DRAFT_CASE_ID ? <Tag color="gold">草稿</Tag> : null}
                            </div>
                            <span className="api-case-nav-item-name">{item.name}</span>
                            <span className="api-case-nav-item-path">{getCaseDisplayPath(item.urlTemplate)}</span>
                          </div>
                          <div className="api-case-nav-item-actions">
                            <Popconfirm
                              title={caseId === DRAFT_CASE_ID ? '确认丢弃这个未保存用例？' : '确认删除该用例？'}
                              onConfirm={() => {
                                if (caseId === DRAFT_CASE_ID) {
                                  setDraftCaseValues(null)
                                  const fallbackCase = filteredCases[0] ?? null
                                  if (fallbackCase) {
                                    setSelectedCaseId(getCaseId(fallbackCase))
                                  } else {
                                    setSelectedCaseId('')
                                    setEditingCase(null)
                                    resetCaseForm()
                                  }
                                  return
                                }
                                deleteCaseMutation.mutate(caseId)
                              }}
                            >
                              <ProjectActionButton action="write"
                                danger
                                type="text"
                                size="small"
                                operation="delete" iconOnly
                                className="api-case-nav-delete"
                                onClick={(event) => event.stopPropagation()}
                                onMouseDown={(event) => event.stopPropagation()}
                              />
                            </Popconfirm>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </aside>

            <div className="api-case-workspace">
              {collectionQuery.data ? (
                <div className="api-detail-hover-panel api-collection-detail-panel">
                  <div className="api-detail-hover-bar">
                    <div className="api-detail-hover-bar-main">
                      <span className="api-detail-hover-title">Collection 详情</span>
                      <span className="api-detail-hover-preview">
                        {collectionQuery.data.name} / {requirementQuery.data?.name ?? requirementId ?? '-'} / {sprintQuery.data?.name ?? sprintId ?? '-'}
                      </span>
                    </div>
                    <div className="api-detail-hover-bar-actions">
                      <Button className="action-btn-read" onClick={() => setCollectionRunHistoryOpen(true)}>运行记录</Button>
                      <Button
                        type="primary"
                        loading={runApiCollectionMutation.isPending}
                        onClick={handleRunCollection}
                        icon={<SendOutlined />}
                        disabled={!resolvedEnvironmentId || cases.length === 0}
                      >
                        运行测试
                      </Button>
                    </div>
                  </div>
                  <div className="api-detail-hover-body">
                    <p className="api-detail-description">
                      {collectionQuery.data.description || '查看当前 Collection 的真实详情与用例列表。'}
                    </p>
                    <Card className="detail-block api-case-summary-card">
                      <div className="api-case-summary-grid compact">
                        <div className="api-summary-item">
                          <Text type="secondary">Collection</Text>
                          <strong>{collectionQuery.data.name}</strong>
                        </div>
                        <div className="api-summary-item">
                          <Text type="secondary">需求</Text>
                          <strong>{requirementQuery.data?.name ?? requirementId ?? '-'}</strong>
                        </div>
                        <div className="api-summary-item">
                          <Text type="secondary">迭代</Text>
                          <strong>{sprintQuery.data?.name ?? sprintId ?? '-'}</strong>
                        </div>
                        <div className="api-summary-item">
                          <Text type="secondary">更新</Text>
                          <strong>{formatTime(pickUpdatedAt(collectionQuery.data))}</strong>
                        </div>
                      </div>
                    </Card>
                  </div>
                </div>
              ) : null}

              <section className="workbench-panel api-case-editor-panel">
                <div className="api-case-editor-shell" ref={editorLayoutRef}>
                  <div className="api-case-editor-main" style={runResult ? { flexBasis: `${editorTopHeight}px` } : undefined}>
                    <div className="api-case-editor-main-scroll">
                      <Form<ApiCaseFormValues>
                        form={caseForm}
                        layout="vertical"
                        requiredMark={false}
                        className="api-case-editor-form"
                        onValuesChange={(_changedValues, allValues) => {
                          if (isCreatingCase) {
                            setDraftCaseValues(allValues as ApiCaseFormValues)
                          }
                        }}
                        onFinish={(values) => {
                          const completeValues = {
                            ...getCompleteCaseFormValues(),
                            ...values,
                            headers: values.headers ?? getCompleteCaseFormValues().headers,
                            query: values.query ?? getCompleteCaseFormValues().query,
                          } satisfies ApiCaseFormValues

                          if (isCreatingCase) {
                            createCaseMutation.mutate(completeValues)
                            return
                          }

                          if (!editingCase || getCaseId(editingCase) !== activeCaseId) {
                            message.warning('用例详情加载中，请稍后再试')
                            return
                          }

                          const payload = buildApiCaseUpdatePayload(editingCase, completeValues)
                          if (Object.keys(payload).length === 0) {
                            message.info('当前没有需要保存的修改')
                            return
                          }

                          updateCaseMutation.mutate(completeValues)
                        }}
                      >
                        <div className="api-case-editor-sticky-head">
                          <Form.Item name="name" label="用例名称" rules={[{ required: true, message: '请输入用例名称' }]}>
                            <Input maxLength={120} />
                          </Form.Item>

                          <div className="api-case-request-shell">
                            <div className="api-case-request-caption">
                              <span>请求地址</span>
                              <span className="api-case-request-env-hint">当前环境</span>
                              <Tooltip title="路径不是 http:// 或 https:// 开头时，会自动拼接当前环境 Base URL。">
                                <InfoCircleOutlined className="api-case-request-info" />
                              </Tooltip>
                            </div>
                            <div className="api-case-request-bar">
                              <Form.Item name="method" className="api-case-method-item" rules={[{ required: true, message: '请选择请求方式' }]}>
                                <Select options={methodOptions} classNames={{ popup: { root: 'api-method-dropdown' } }} />
                              </Form.Item>
                              <div className="api-case-url-group">
                                <Popover
                                  trigger="click"
                                  placement="bottomLeft"
                                  open={environmentPopoverOpen}
                                  onOpenChange={setEnvironmentPopoverOpen}
                                  overlayClassName="api-case-environment-popover-overlay"
                                  content={
                                    <div className="api-case-environment-popover">
                                      <div className="api-case-environment-popover-head">
                                        <div className="api-case-environment-popover-title">选择环境 Base URL</div>
                                        <div className="api-case-environment-popover-tip">
                                          当路径不是 http:// 或 https:// 开头时，会自动拼接当前环境的 Base URL。
                                        </div>
                                        <div className="api-case-environment-popover-subtitle">选中后会切换为当前启用环境</div>
                                      </div>
                                      <div className="api-case-environment-option-list">
                                      {environments.length === 0 ? (
                                        <div className="api-case-environment-empty">当前项目还没有可用环境</div>
                                      ) : (
                                        environments.map((environment) => {
                                          const environmentId = normalizeEnvironmentId(environment)
                                          const active = environmentId === resolvedEnvironmentId

                                          return (
                                            <button
                                              key={environmentId}
                                              type="button"
                                              className={`api-case-environment-option${active ? ' active' : ''}`}
                                              onClick={() => handleSelectEnvironment(environmentId)}
                                              disabled={switchDefaultEnvironmentMutation.isPending}
                                            >
                                                <span className="api-case-environment-option-main">
                                                  <span className="api-case-environment-option-url">{environment.baseUrl}</span>
                                                  <span className="api-case-environment-option-name">
                                                    {environment.name}
                                                    {environment.isDefault ? ' · 启用中' : ''}
                                                  </span>
                                                </span>
                                              {active ? <span className="api-case-environment-option-badge">当前</span> : null}
                                            </button>
                                          )
                                        })
                                      )}
                                    </div>
                                  </div>
                                }
                                >
                                  <button
                                    type="button"
                                    className={`api-case-base-url-trigger${environmentPopoverOpen ? ' open' : ''}`}
                                    disabled={!projectId || environments.length === 0}
                                    title={selectedEnvironment?.baseUrl || '未选择环境'}
                                  >
                                    <span className="api-case-base-url-text">
                                      {selectedEnvironment?.baseUrl || (environmentsQuery.isLoading ? '加载环境中...' : '未选择环境')}
                                    </span>
                                    <DownOutlined className="api-case-base-url-arrow" />
                                  </button>
                                </Popover>
                                <span className="api-case-url-divider" aria-hidden="true" />
                                <Form.Item name="path" className="api-case-path-item" rules={[{ required: true, message: '请输入接口路径' }]}>
                                  <Input ref={pathInputRef} placeholder="/v1/example" maxLength={1024} />
                                </Form.Item>
                              </div>
                              <div className="api-case-request-actions">
                                <Button
                                  type="primary"
                                  className="api-case-send-button"
                                  loading={runApiCaseMutation.isPending || isApiCaseRunInProgress}
                                  disabled={!isSelectedCaseReady || isApiCaseRunInProgress}
                                  onClick={handleSendRequest}
                                  icon={<SendOutlined />}
                                >
                                  发送
                                </Button>
                                <ProjectActionButton operation="save" action="write"
                                  className="api-case-save-button"
                                  loading={createCaseMutation.isPending || updateCaseMutation.isPending}
                                  disabled={!isSelectedCaseReady}
                                  onClick={() => caseForm.submit()}
                                >
                                  保存
                                </ProjectActionButton>
                              </div>
                            </div>
                          </div>
                        </div>

                        <Tabs
                          className="api-case-editor-tabs"
                          items={[
                            {
                              key: 'query',
                              label: '参数',
                              children: (
                                <>
                                  <Form.List name="query">
                                    {(fields, { remove }) => (
                                      <div className="api-kv-block">
                                        <div className="api-kv-toolbar">
                                          <Text strong>Query 参数</Text>
                                        </div>
                                        {fields.map((field) => {
                                          const { key: fieldKey, ...fieldProps } = field

                                          return (
                                          <div key={fieldKey} className="api-kv-row">
                                            <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-kv-check-item">
                                              <Switch size="small" />
                                            </Form.Item>
                                            <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-kv-item">
                                              <Input placeholder="参数名" />
                                            </Form.Item>
                                            <div className="api-kv-item api-kv-value-item">
                                              <Space.Compact style={{ width: '100%' }}>
                                                <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                                                  <Input
                                                    ref={(node) => setEnvVarInputRef(`query:${field.key}:value`, node)}
                                                    placeholder="参数值"
                                                  />
                                                </Form.Item>
                                                {renderEnvVarPicker({
                                                  pickerKey: `query:${field.key}:value`,
                                                  onInsert: (templateText) => insertTemplateText(['query', field.name, 'value'], `query:${field.key}:value`, templateText),
                                                  trigger: <Button type="text" size="small" className="api-env-var-picker-trigger" icon={<CodeOutlined />} />,
                                                })}
                                              </Space.Compact>
                                            </div>
                                            <Tooltip title="删除参数">
                                              <ProjectActionButton action="write"
                                                danger
                                                type="text"
                                                shape="circle"
                                                className="action-btn-delete"
                                                operation="delete" iconOnly
                                                aria-label="删除参数"
                                                onClick={() => remove(field.name)}
                                              />
                                            </Tooltip>
                                          </div>
                                          )
                                        })}
                                      </div>
                                    )}
                                  </Form.List>
                                </>
                              ),
                            },
                            {
                              key: 'headers',
                              label: '请求头',
                              children: (
                                <Form.List name="headers">
                                  {(fields, { remove }) => (
                                    <div className="api-kv-block">
                                      <div className="api-kv-toolbar">
                                        <Text strong>请求头</Text>
                                      </div>
                                      {fields.map((field) => {
                                        const { key: fieldKey, ...fieldProps } = field

                                        return (
                                        <div key={fieldKey} className="api-kv-row">
                                          <Form.Item {...fieldProps} name={[field.name, 'enabled']} valuePropName="checked" className="api-kv-check-item">
                                            <Switch size="small" />
                                          </Form.Item>
                                          <Form.Item {...fieldProps} name={[field.name, 'key']} className="api-kv-item">
                                            <Input placeholder="Header 名称" />
                                          </Form.Item>
                                          <div className="api-kv-item api-kv-value-item">
                                            <Space.Compact style={{ width: '100%' }}>
                                              <Form.Item {...fieldProps} name={[field.name, 'value']} noStyle>
                                                <Input
                                                  ref={(node) => setEnvVarInputRef(`headers:${field.key}:value`, node)}
                                                  placeholder="Header 值"
                                                />
                                              </Form.Item>
                                              {renderEnvVarPicker({
                                                pickerKey: `headers:${field.key}:value`,
                                                onInsert: (templateText) => insertTemplateText(['headers', field.name, 'value'], `headers:${field.key}:value`, templateText),
                                                trigger: <Button type="text" size="small" className="api-env-var-picker-trigger" icon={<CodeOutlined />} />,
                                              })}
                                            </Space.Compact>
                                          </div>
                                          <Tooltip title="删除请求头">
                                            <ProjectActionButton action="write"
                                              danger
                                              type="text"
                                              shape="circle"
                                              className="action-btn-delete"
                                              operation="delete" iconOnly
                                              aria-label="删除请求头"
                                              onClick={() => remove(field.name)}
                                            />
                                          </Tooltip>
                                        </div>
                                        )
                                      })}
                                    </div>
                                  )}
                                </Form.List>
                              ),
                            },
                            {
                              key: 'body',
                              label: '请求体',
                              children: (
                                <>
                                  <Form.Item name="bodyType" hidden>
                                    <Input />
                                  </Form.Item>
                                  <div className="api-body-type-block">
                                    <Segmented
                                      className="api-body-type-segmented"
                                      options={bodyTypeOptions}
                                      value={watchedBodyType ?? 'none'}
                                      onChange={(value) => caseForm.setFieldValue('bodyType', value)}
                                    />
                                  </div>
                                  {watchedBodyType === 'json' ? (
                                    <Form.Item
                                      name="bodyJson"
                                      className="api-body-editor-form-item"
                                      validateTrigger={['onChange', 'onBlur']}
                                      rules={[
                                        {
                                          validator: async (_, value) => validateJsonText(value),
                                        },
                                      ]}
                                    >
                                      <JsonEditor
                                        ref={bodyJsonEditorRef}
                                        minHeight={260}
                                        toolbar={
                                          <div className="json-editor-toolbar-row">
                                            <div className="json-editor-toolbar-actions">
                                              {renderEnvVarPicker({
                                                pickerKey: 'bodyJson',
                                                placement: 'bottomLeft',
                                                onInsert: insertTemplateTextIntoJson,
                                                trigger: (
                                                  <Button className="json-editor-toolbar-btn" icon={<CodeOutlined />}>
                                                    动态值
                                                    <DownOutlined />
                                                  </Button>
                                                ),
                                              })}
                                            </div>
                                            <div className="json-editor-toolbar-side">
                                              <span className="json-editor-toolbar-type">application/json</span>
                                              <Button type="text" className="json-editor-toolbar-link" onClick={handleFormatBodyJson}>
                                                格式化
                                              </Button>
                                            </div>
                                          </div>
                                        }
                                      />
                                    </Form.Item>
                                  ) : null}
                                  {watchedBodyType === 'raw' ? (
                                    <Form.Item name="bodyText" label="Body 内容">
                                      <Input.TextArea rows={8} placeholder="原始请求体内容" />
                                    </Form.Item>
                                  ) : null}
                                  {watchedBodyType === 'form' ? (
                                    <Card size="small" className="api-body-placeholder-card">
                                      <Text type="secondary">`form` 类型的键值表单下一步再补，这一版先保留类型切换。</Text>
                                    </Card>
                                  ) : null}
                                  {watchedBodyType === 'none' ? (
                                    <Card size="small" className="api-body-placeholder-card">
                                      <Text type="secondary">当前选择 `none`，无需填写请求体。</Text>
                                    </Card>
                                  ) : null}
                                </>
                              ),
                            },
                            {
                              key: 'settings',
                              label: '设置',
                              children: (
                                <div className="api-case-settings-grid">
                                  <Form.Item name="timeoutMs" label="超时时间(ms)">
                                    <InputNumber min={0} step={1000} style={{ width: '100%' }} />
                                  </Form.Item>
                                  <Form.Item name="enabled" label="是否启用" valuePropName="checked">
                                    <Switch />
                                  </Form.Item>
                                  <Form.Item name="continueOnFailure" label="失败后继续" valuePropName="checked">
                                    <Switch />
                                  </Form.Item>
                                  <Form.Item name="description" label="用例描述" className="api-case-settings-description">
                                    <Input.TextArea rows={6} maxLength={512} />
                                  </Form.Item>
                                </div>
                              ),
                            },
                            {
                              key: 'post-operations',
                              label: `后置操作 (${postOperationCount})`,
                              children: activeCaseId ? (
                                <div className="api-post-ops-section">
                                  <div className="api-post-ops-head">
                                    <div className="api-post-ops-head-main">
                                      <Text strong>后置操作</Text>
                                      <div className="api-post-ops-subtitle">统一管理断言与提取变量，提取结果会写回当前所选环境变量。</div>
                                    </div>
                                  </div>

                                  <Dropdown
                                    disabled={!can('write')}
                                    trigger={['click']}
                                    menu={{
                                      items: [
                                        { key: 'assert', label: '新增断言' },
                                        { key: 'extract', label: '新增提取规则' },
                                      ],
                                      onClick: ({ key }) => {
                                        if (key === 'assert') {
                                          openCreateAssertRule()
                                          return
                                        }
                                        openCreateExtractRule()
                                      },
                                    }}
                                  >
                                    <ProjectActionButton action="write" type="text" className="api-post-ops-add-trigger">
                                      <PlusOutlined />
                                      <span>添加后置操作</span>
                                      <DownOutlined />
                                    </ProjectActionButton>
                                  </Dropdown>

                                  {assertRulesQuery.isLoading || extractRulesQuery.isLoading ? (
                                    <Empty description="后置操作加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                                  ) : postOperationCount === 0 ? (
                                    <Card size="small" className="api-rule-empty-card">
                                      <Empty description="还没有后置操作，点击上方添加断言或提取规则" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                                    </Card>
                                  ) : (
                                    <div className="api-post-ops-group-list">
                                      <div className="api-post-ops-group">
                                        <div className="api-post-ops-group-title">
                                          <span>断言</span>
                                          <Tag>{assertRules.length}</Tag>
                                        </div>
                                        {assertRules.length === 0 ? (
                                          <div className="api-post-ops-empty">暂无断言规则</div>
                                        ) : (
                                          <div className="api-post-ops-items">
                                            {assertRules.map((rule) => (
                                              <div key={normalizeAssertRuleId(rule)} className="api-post-ops-item">
                                                <div className="api-post-ops-item-side">
                                                  <Tag color="error">断言</Tag>
                                                  <Switch
                                                    size="small"
                                                    checked={rule.enabled}
                                                    loading={toggleAssertRuleMutation.isPending}
                                                    onChange={(checked) =>
                                                      toggleAssertRuleMutation.mutate({
                                                        assertRuleId: normalizeAssertRuleId(rule),
                                                        enabled: checked,
                                                      })
                                                    }
                                                  />
                                                </div>
                                                <div className="api-post-ops-item-main">
                                                  <div className="api-post-ops-item-title">
                                                    <strong>{rule.name}</strong>
                                                    <span>#{rule.orderNo ?? '-'}</span>
                                                  </div>
                                                  <div className="api-post-ops-item-meta">
                                                    <span>{assertSourceLabelMap[rule.assertSource]}</span>
                                                    <span>{assertComparatorLabelMap[rule.comparator]}</span>
                                                    <span>{formatOptionalValue(rule.targetExpr)}</span>
                                                    <span>{formatOptionalValue(rule.expectedValue)}</span>
                                                  </div>
                                                </div>
                                                <div className="api-post-ops-item-actions">
                                                  <ProjectActionButton action="write" type="text" size="small" operation="edit" iconOnly onClick={() => openEditAssertRule(rule)} />
                                                  <Popconfirm
                                                    title="确认删除该断言规则？"
                                                    onConfirm={() => deleteAssertRuleMutation.mutate(normalizeAssertRuleId(rule))}
                                                  >
                                                    <ProjectActionButton action="write" danger type="text" size="small" operation="delete" iconOnly loading={deleteAssertRuleMutation.isPending} />
                                                  </Popconfirm>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>

                                      <div className="api-post-ops-group">
                                        <div className="api-post-ops-group-title">
                                          <span>提取规则</span>
                                          <Tag>{extractRules.length}</Tag>
                                        </div>
                                        {extractRules.length === 0 ? (
                                          <div className="api-post-ops-empty">暂无提取规则</div>
                                        ) : (
                                          <div className="api-post-ops-items">
                                            {extractRules.map((rule) => (
                                              <div key={normalizeExtractRuleId(rule)} className="api-post-ops-item">
                                                <div className="api-post-ops-item-side">
                                                  <Tag color="processing">提取</Tag>
                                                  <Switch
                                                    size="small"
                                                    checked={rule.enabled}
                                                    loading={toggleExtractRuleMutation.isPending}
                                                    onChange={(checked) =>
                                                      toggleExtractRuleMutation.mutate({
                                                        extractRuleId: normalizeExtractRuleId(rule),
                                                        enabled: checked,
                                                      })
                                                    }
                                                  />
                                                </div>
                                                <div className="api-post-ops-item-main">
                                                  <div className="api-post-ops-item-title">
                                                    <strong>{rule.name}</strong>
                                                    <span>#{rule.orderNo ?? '-'}</span>
                                                  </div>
                                                  <div className="api-post-ops-item-meta">
                                                    <span>{extractSourceLabelMap[rule.source]}</span>
                                                    <span>{formatOptionalValue(rule.sourceExpr)}</span>
                                                    <span>{formatOptionalValue(rule.varKey)}</span>
                                                    <span>{formatOptionalValue(rule.defaultValue)}</span>
                                                  </div>
                                                </div>
                                                <div className="api-post-ops-item-actions">
                                                  <ProjectActionButton action="write" type="text" size="small" operation="edit" iconOnly onClick={() => openEditExtractRule(rule)} />
                                                  <Popconfirm
                                                    title="确认删除该提取规则？"
                                                    onConfirm={() => deleteExtractRuleMutation.mutate(normalizeExtractRuleId(rule))}
                                                  >
                                                    <ProjectActionButton action="write" danger type="text" size="small" operation="delete" iconOnly loading={deleteExtractRuleMutation.isPending} />
                                                  </Popconfirm>
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <Card size="small" className="api-rule-empty-card">
                                  <Empty description="请先保存当前用例后再配置后置操作" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                                </Card>
                              ),
                            },
                          ]}
                        />
                      </Form>
                    </div>
                  </div>
                  {runResult ? (
                    <>
                      <div
                        className={`api-case-editor-splitter${isResizingEditor ? ' resizing' : ''}`}
                        role="separator"
                        aria-orientation="horizontal"
                        onPointerDown={handleEditorSplitterPointerDown}
                      >
                        <span className="api-case-editor-splitter-line" />
                        <span className="api-case-editor-splitter-grip">⋯</span>
                      </div>
                      <div className="api-case-editor-result-pane">
                        <div className="api-case-editor-result-scroll">
                          <Card size="small" className="api-case-run-result-card">
                            <div className="api-case-run-result-head">
                              <div className="api-case-run-result-title">
                                <Text strong>请求结果</Text>
                                <Tag color={runResultStatusMeta.color}>{runResultStatusMeta.label}</Tag>
                              </div>
                              <div className="api-case-run-result-meta">
                                <span>环境：{selectedEnvironment?.name ?? runResult.environmentId ?? '-'}</span>
                                <span>耗时：{runResult.durationMs ?? 0} ms</span>
                                <span>状态码：{runResult.response?.statusCode ?? '-'}</span>
                                <span>提取失败：{failedExtractCount}</span>
                                <span>断言失败：{failedAssertCount}</span>
                              </div>
                            </div>
                            {runResult.errorMessage ? <Alert showIcon type="error" title={runResult.errorMessage} className="api-case-run-result-alert" /> : null}
                            <Segmented
                              className="api-case-run-result-segmented"
                              options={runResultViewOptions}
                              value={runResultView}
                              onChange={(value) => setRunResultView(value as typeof runResultView)}
                            />
                            <div className="api-case-run-result-block">
                              {renderRunResultContent({
                                view: runResultView,
                                request: runResult.request,
                                response: runResult.response,
                                extractResults,
                                assertResults,
                              })}
                            </div>
                          </Card>
                        </div>
                      </div>
                    </>
                  ) : null}
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>

      <ProjectActionModal action="execute"
        mask={{ closable: false }}
        open={caseImportModalOpen}
        title="用例导入"
        width={860}
        okText="开始导入"
        onCancel={closeCaseImportModal}
        confirmLoading={importApiCasesMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        onOk={handleImportApiCases}
        rootClassName="api-case-import-modal-root"
        className="api-case-import-modal-shell"
        destroyOnHidden
      >
        <div className="api-case-import-modal">
          <Segmented
            className="api-case-import-mode"
            value={caseImportMode}
            options={[
              { label: '上传 YAML', value: 'upload' },
              { label: '直接输入', value: 'editor' },
            ]}
            onChange={(value) => setCaseImportMode(value as CaseImportMode)}
          />
          {caseImportMode === 'upload' ? (
            <div className="api-case-import-upload">
              <Upload.Dragger
                accept=".yaml,.yml"
                maxCount={1}
                beforeUpload={(file) => {
                  if (!isYamlFileName(file.name)) {
                    message.error('仅支持 .yaml 或 .yml 文件')
                    return Upload.LIST_IGNORE
                  }
                  setImportYamlFile(file)
                  return false
                }}
                onRemove={() => {
                  setImportYamlFile(null)
                  return true
                }}
              >
                <p className="ant-upload-drag-icon">
                  <UploadOutlined />
                </p>
                <p className="ant-upload-text">点击或拖拽 YAML 文件到这里</p>
                <p className="ant-upload-hint">仅支持 .yaml / .yml，导入时会自动绑定到当前 Collection。</p>
              </Upload.Dragger>
              <div className="api-case-import-hint">后端会直接解析 YAML，前端不做字段预解析。</div>
            </div>
          ) : (
            <div className="api-case-import-editor">
              <div className="api-case-import-hint">直接粘贴 YAML 内容，提交时前端会将文本包装成 `.yaml` 文件上传。</div>
              <TextCodeEditor value={importYamlText} onChange={setImportYamlText} language="yaml" minHeight={280} />
            </div>
          )}
        </div>
      </ProjectActionModal>

      <Modal
        mask={{ closable: false }}
        open={collectionRunHistoryOpen}
        title="运行记录"
        width={760}
        footer={null}
        onCancel={() => setCollectionRunHistoryOpen(false)}
        destroyOnHidden={false}
        className="api-collection-run-history-modal"
      >
        <div className="api-collection-run-history-layout">
          {collectionRunHistoryQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(collectionRunHistoryQuery.error)} />
          ) : collectionRunHistoryQuery.isLoading ? (
            <Empty description="运行记录加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : collectionRunHistory.length === 0 ? (
            <Empty description="暂无运行记录" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <div className="api-collection-run-history-list">
              {collectionRunHistory.map((item, index) => {
                const statusMeta = getExecutionStatusMeta(item.status)
                const isLoading = loadingCollectionRunHistoryId === item.collectionRunId
                const environmentName =
                  environments.find((environment) => normalizeEnvironmentId(environment) === item.environmentId)?.name ?? item.environmentId ?? '-'

                return (
                  <button
                    key={item.collectionRunId ?? `collection-run-${index}`}
                    type="button"
                    className="api-collection-run-history-item"
                    onClick={() => handleOpenCollectionRunHistoryItem(item)}
                    disabled={Boolean(loadingCollectionRunHistoryId)}
                  >
                    <div className="api-collection-run-history-item-main">
                      <div className="api-collection-run-history-item-title">
                        <strong>{formatTime(item.startedAt || item.createdAt || item.updatedAt)}</strong>
                        <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                        <Tag>{environmentName}</Tag>
                      </div>
                      <div className="api-collection-run-history-item-meta">
                        <span>总数：{item.totalCount ?? 0}</span>
                        <span>成功：{item.successCount ?? 0}</span>
                        <span>失败：{item.failedCount ?? 0}</span>
                        <span>异常：{item.errorCount ?? 0}</span>
                        <span>跳过：{item.skippedCount ?? 0}</span>
                        <span>耗时：{item.durationMs ?? 0} ms</span>
                        <span>结束：{formatTime(item.finishedAt)}</span>
                      </div>
                      {item.errorMessage ? <div className="api-collection-run-history-item-error">{item.errorMessage}</div> : null}
                    </div>
                    <div className="api-collection-run-history-item-side">
                      <span className="api-collection-run-history-item-id">{item.collectionRunId ?? '-'}</span>
                      <span className="api-collection-run-history-item-link">{isLoading ? '加载中...' : '查看报告'}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </Modal>

      <Modal
        mask={{ closable: false }}
        open={collectionRunReportOpen}
        title="API测试集报告"
        width={1180}
        footer={null}
        onCancel={() => {
          setCollectionRunReportOpen(false)
          setSelectedCollectionRunId('')
        }}
        destroyOnHidden={false}
        rootClassName="api-collection-run-report-modal-root"
        className="api-collection-run-report-modal"
      >
        {collectionRunReportQuery.error && !collectionRunReport ? (
          <Alert showIcon type="error" title={getErrorMessage(collectionRunReportQuery.error)} />
        ) : collectionRunReportQuery.isLoading && !collectionRunReport ? (
          <Empty description="API测试集报告加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : collectionRunReport ? (
          <div className="api-collection-run-report-layout">
            <div className="api-collection-run-report-static">
              <div className="api-collection-run-report-head">
                <div className="api-collection-run-report-head-main">
                  <div className="api-collection-run-report-title">
                    <Text strong>运行结果</Text>
                    <Tag color={getExecutionStatusMeta(collectionRunReport.status).color}>{getExecutionStatusMeta(collectionRunReport.status).label}</Tag>
                  </div>
                  <div className="api-collection-run-report-meta">
                    <span>
                      环境：
                      {environments.find((environment) => normalizeEnvironmentId(environment) === collectionRunReport.environmentId)?.name ??
                        collectionRunReport.environmentId ??
                        '-'}
                    </span>
                    <span>开始：{formatTime(collectionRunReport.startedAt)}</span>
                    <span>结束：{formatTime(collectionRunReport.finishedAt)}</span>
                    <span>总耗时：{collectionRunReport.durationMs ?? 0} ms</span>
                  </div>
                </div>
                <div className="api-collection-run-report-head-actions">
                  <ActionButton operation="download" onClick={handleExportCollectionRunReportHtml} disabled={!collectionRunReport}>
                    导出 HTML
                  </ActionButton>
                  <Button
                    onClick={handleRefreshCollectionRunReport}
                    loading={refreshingCollectionRunReport}
                    disabled={!selectedCollectionRunId}
                  >
                    刷新报告
                  </Button>
                </div>
              </div>

              <div className="api-collection-run-report-summary-grid">
                <div className="api-collection-run-report-summary-item">
                  <span>总数</span>
                  <strong>{collectionRunReport.totalCount ?? 0}</strong>
                </div>
                <div className="api-collection-run-report-summary-item success">
                  <span>成功</span>
                  <strong>{collectionRunReport.successCount ?? 0}</strong>
                </div>
                <div className="api-collection-run-report-summary-item failed">
                  <span>失败</span>
                  <strong>{collectionRunReport.failedCount ?? 0}</strong>
                </div>
                <div className="api-collection-run-report-summary-item error">
                  <span>异常</span>
                  <strong>{collectionRunReport.errorCount ?? 0}</strong>
                </div>
                <div className="api-collection-run-report-summary-item skipped">
                  <span>跳过</span>
                  <strong>{collectionRunReport.skippedCount ?? 0}</strong>
                </div>
                <div className="api-collection-run-report-summary-item">
                  <span>报告 ID</span>
                  <strong>{collectionRunReport.collectionRunId ?? '-'}</strong>
                </div>
              </div>

              {collectionRunReport.errorMessage ? (
                <Alert showIcon type="error" title={collectionRunReport.errorMessage} className="api-case-run-result-alert" />
              ) : null}

              <Segmented
                className="api-case-run-result-segmented"
                options={collectionReportViewOptions}
                value={collectionRunReportView}
                onChange={(value) => setCollectionRunReportView(value as CollectionReportView)}
              />
            </div>

            <div className="api-collection-run-report-scroll">
              <div className="api-collection-run-report-content">
                {collectionRunReportView === 'runtime' ? (
                  <pre className="api-case-run-result-pre compact">
{JSON.stringify(parseMaybeJsonValue(collectionRunReport.runtimeVarsJson), null, 2)}
                  </pre>
                ) : orderedCollectionRunItems.length === 0 ? (
                  <Empty description="暂无API测试集运行明细" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div className="api-collection-run-report-list">
                    {orderedCollectionRunItems.map((item, index) => {
                      const itemKey = getCollectionRunItemKey(item, index)
                      const expanded = expandedCollectionRunItemIds.includes(itemKey)
                      const itemView = collectionRunItemViews[itemKey] ?? 'response'
                      const statusMeta = getExecutionStatusMeta(item.status)
                      const itemExtractResults = item.extractResults ?? []
                      const itemAssertResults = item.assertResults ?? []

                      return (
                        <div key={itemKey} className={`api-collection-run-report-item${expanded ? ' expanded' : ''}`}>
                          <button type="button" className="api-collection-run-report-item-head" onClick={() => toggleCollectionRunItem(itemKey)}>
                            <div className="api-collection-run-report-item-title">
                              <span className="api-collection-run-report-item-order">#{item.orderNo ?? index + 1}</span>
                              <strong>{item.caseName || `用例 ${index + 1}`}</strong>
                              <Tag color={statusMeta.color}>{statusMeta.label}</Tag>
                              {item.continueOnFailure ? <Tag color="processing">失败后继续</Tag> : null}
                            </div>
                            <div className="api-collection-run-report-item-meta">
                              <span>耗时：{item.durationMs ?? 0} ms</span>
                              <span>开始：{formatTime(item.startedAt)}</span>
                              <span>结束：{formatTime(item.finishedAt)}</span>
                              <DownOutlined className={`api-collection-run-report-item-arrow${expanded ? ' expanded' : ''}`} />
                            </div>
                          </button>

                          {expanded ? (
                            <div className="api-collection-run-report-item-body">
                              <div className="api-collection-run-report-item-inline-meta">
                                <span>caseId：{item.caseId || '-'}</span>
                                <span>caseRunId：{item.caseRunId || '-'}</span>
                                <span>状态码：{item.response?.statusCode ?? '-'}</span>
                                <span>提取失败：{itemExtractResults.filter((result) => !result.success).length}</span>
                                <span>断言失败：{itemAssertResults.filter((result) => !result.success).length}</span>
                              </div>
                              {item.errorMessage ? <Alert showIcon type="error" title={item.errorMessage} className="api-case-run-result-alert" /> : null}
                              <Segmented
                                className="api-case-run-result-segmented"
                                options={runResultViewOptions}
                                value={itemView}
                                onChange={(value) => handleCollectionRunItemViewChange(itemKey, value as RunResultView)}
                              />
                              <div className="api-case-run-result-block">
                                {renderRunResultContent({
                                  view: itemView,
                                  request: item.request,
                                  response: item.response,
                                  extractResults: itemExtractResults,
                                  assertResults: itemAssertResults,
                                  emptyExtractDescription: '该用例没有提取结果',
                                  emptyAssertDescription: '该用例没有断言结果',
                                })}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <Empty description={isApiRunPollingStatus(selectedCollectionRunSummary?.status) ? '运行中，报告生成中...' : '暂无API测试集报告'} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Modal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        open={assertRuleModalOpen}
        title={editingAssertRule ? '编辑断言规则' : '新增断言规则'}
        okText="保存"
        onCancel={() => {
          setAssertRuleModalOpen(false)
          setEditingAssertRule(null)
          assertRuleForm.resetFields()
        }}
        confirmLoading={saveAssertRuleMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        onOk={() => assertRuleForm.submit()}
        destroyOnHidden
      >
        <Form<AssertRuleFormValues>
          form={assertRuleForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => saveAssertRuleMutation.mutate(values)}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input maxLength={120} />
          </Form.Item>
          <div className="api-rule-form-grid">
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="orderNo" label="顺序">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className="api-rule-form-grid">
            <Form.Item name="assertSource" label="来源" rules={[{ required: true, message: '请选择来源' }]}>
              <Select options={assertSourceOptions} />
            </Form.Item>
            <Form.Item name="comparator" label="比较方式" rules={[{ required: true, message: '请选择比较方式' }]}>
              <Select options={assertComparatorOptions} />
            </Form.Item>
          </div>
          <Form.Item name="targetExpr" label="目标表达式" extra={watchedAssertSource === 'status_code' ? 'status_code 场景可留空。' : undefined}>
            <Input placeholder={watchedAssertSource === 'status_code' ? '可留空' : '例如：$.data.token'} />
          </Form.Item>
          <Form.Item
            name="expectedValue"
            label="期望值"
            extra={watchedAssertComparator === 'exists' ? 'exists 断言可留空。' : undefined}
          >
            <Input placeholder={watchedAssertComparator === 'exists' ? '可留空' : '填写期望结果'} />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        open={extractRuleModalOpen}
        title={editingExtractRule ? '编辑提取规则' : '新增提取规则'}
        okText="保存"
        onCancel={() => {
          setExtractRuleModalOpen(false)
          setEditingExtractRule(null)
          extractRuleForm.resetFields()
        }}
        confirmLoading={saveExtractRuleMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        onOk={() => extractRuleForm.submit()}
        destroyOnHidden
      >
        <Form<ExtractRuleFormValues>
          form={extractRuleForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => saveExtractRuleMutation.mutate(values)}
        >
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入规则名称' }]}>
            <Input maxLength={120} />
          </Form.Item>
          <div className="api-rule-form-grid">
            <Form.Item name="enabled" label="启用" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="orderNo" label="顺序">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className="api-rule-form-grid">
            <Form.Item name="source" label="来源" rules={[{ required: true, message: '请选择来源' }]}>
              <Select options={extractSourceOptions} />
            </Form.Item>
            <Form.Item
              name="varKey"
              label="写回变量 Key"
              extra="运行后会写回当前所选环境；同名变量存在时更新，不存在时自动创建。"
              rules={[{ required: true, message: '请输入写回变量 Key' }]}
            >
              <Input maxLength={120} placeholder="例如：token" />
            </Form.Item>
          </div>
          <Form.Item name="sourceExpr" label="来源表达式">
            <Input placeholder={watchedExtractSource === 'status_code' ? '可留空' : '例如：$.data.token'} />
          </Form.Item>
          <Form.Item name="defaultValue" label="默认值">
            <Input placeholder="提取失败时回退" />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      {renderEnvVarPickerModal()}
    </div>
  )}</ProjectAccessScope>)
}
