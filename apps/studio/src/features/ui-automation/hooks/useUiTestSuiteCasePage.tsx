import { CodeOutlined } from '@ant-design/icons'
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Form, Modal, type InputRef } from 'antd'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import { getRunEventFallbackInterval, getRunPollingInterval, RUN_HISTORY_POLL_INTERVAL } from '@/domain/runs/polling'
import { refreshRunQuery } from '@/domain/runs/refreshRunQuery'
import { DebugStreamUnavailable, startDebugStream } from '@/domain/runs/startDebugStream'
import { useRunEvents } from '@/domain/runs/useRunEvents'
import { useRunReportRefresh } from '@/domain/runs/useRunReportRefresh'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import {
  api,
  ApiError,
  listItems,
  type UiMissingVariable,
  type UiTestCase,
  type UiTestCaseRun,
  type UiTestSuiteRunSummary,
} from '@/services/api'
import { listTotal } from '@/shared/api/request'
import type { CaseImportMode } from '@/shared/utils/caseImport'
import { message } from '@/shared/utils/feedback'
import { compareByOrderNo } from '@/shared/utils/order'
import { getErrorMessage, normalizeUiTestCaseId } from '@/utils/format'
import { buildUiTestCaseUpdatePayload } from '@/utils/updatePayload'
import type { FlowItem, UiExecutionFlowHandle } from '../components/UiExecutionFlow'
import type { UiSuiteRunReportView } from '../config/stepConfig'
import { formatUiScreenshotPolicy } from '../constants/defaultRunConfig'
import { isYamlFileName, type UiTemplateFieldKey } from '../utils/detailView'
import { formatUiCaseSerial, formatUiRunRelativeTime, getUiSuiteReadiness } from '../utils/detailRunView'
import {
  buildUiSuiteDebugRunPayload,
  buildUiSuiteRunPayload,
  getUiTestCaseRunId,
  getUiTestSuiteRunId,
  isUiRunPollingStatus,
} from '../utils/runHelpers'
import {
  DRAFT_CASE_ID,
  EMPTY_UI_TEST_CASES,
  buildUiTestCaseFormValues,
  createDefaultUiTestCaseFormValues,
  getUiTestCaseStepCount,
  moveExpandedStepIndex,
  serializeSteps,
  serializeUiTestCaseValues,
  sortUiTestCases,
  type UiTestCaseFormValues,
  type UiTestStepFormValue,
} from '../utils/uiTestCaseEditor'

const RUN_HISTORY_PAGE_SIZE = 20

export function useUiTestSuiteCasePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { suiteId = '' } = useParams<{ suiteId: string }>()
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [caseDirty, setCaseDirty] = useState(false)
  const stepFlowRef = useRef<UiExecutionFlowHandle>(null)
  const caseFlowRef = useRef<UiExecutionFlowHandle>(null)
  const [flowLevel, setFlowLevel] = useState<'cases' | 'steps'>('cases')
  const [selectedStepIndex, setSelectedStepIndex] = useState(0)
  const [stepConfigHost, setStepConfigHost] = useState<HTMLDivElement | null>(null)
  const [stepConfigTab, setStepConfigTab] = useState<'basic' | 'extract'>('basic')
  const [draftCaseValues, setDraftCaseValues] = useState<UiTestCaseFormValues | null>(null)
  const [editingCase, setEditingCase] = useState<UiTestCase | null>(null)
  const [caseOrderIds, setCaseOrderIds] = useState<string[]>([])
  const [expandedStepIndexes, setExpandedStepIndexes] = useState<number[]>([])
  const [draggingStepIndex, setDraggingStepIndex] = useState<number | null>(null)
  const [selectedRunId, setSelectedRunId] = useState('')
  const [liveUiRunId, setLiveUiRunId] = useState('')
  const debugStreamRef = useRef<{ abort: () => void } | null>(null)
  useEffect(() => () => { debugStreamRef.current?.abort() }, [])
  const [suiteRunHistoryOpen, setSuiteRunHistoryOpen] = useState(false)
  const [suiteRunReportOpen, setSuiteRunReportOpen] = useState(false)
  const [selectedSuiteRunId, setSelectedSuiteRunId] = useState('')
  const [activePollingSuiteRunId, setActivePollingSuiteRunId] = useState('')
  const [loadingSuiteRunHistoryId, setLoadingSuiteRunHistoryId] = useState('')
  const [refreshingSuiteRunReport, setRefreshingSuiteRunReport] = useState(false)
  const [suiteRunReportView, setSuiteRunReportView] = useState<UiSuiteRunReportView>('items')
  const [expandedSuiteRunItemIds, setExpandedSuiteRunItemIds] = useState<string[]>([])
  const [caseImportModalOpen, setCaseImportModalOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importYamlFile, setImportYamlFile] = useState<File | null>(null)
  const [importYamlText, setImportYamlText] = useState('')
  const [templatePickerTarget, setTemplatePickerTarget] = useState<{ stepIndex: number; fieldKey: UiTemplateFieldKey } | null>(null)
  const [caseForm] = Form.useForm<UiTestCaseFormValues>()
  const caseOrderRollbackRef = useRef<string[]>([])
  const templateInputRefs = useRef<Record<string, InputRef | null>>({})

  const suiteQuery = useQuery({
    queryKey: ['uiTestSuite', suiteId],
    queryFn: () => api.getUiTestSuite(suiteId),
    enabled: Boolean(suiteId),
  })

  const requirementId = suiteQuery.data?.requirementId ?? suiteQuery.data?.requirement_id ?? ''

  const requirementQuery = useQuery({
    queryKey: ['requirement', requirementId],
    queryFn: () => api.getRequirement(requirementId),
    enabled: Boolean(requirementId),
  })

  const sprintId = requirementQuery.data?.sprintId ?? requirementQuery.data?.sprint_id ?? ''

  const sprintQuery = useQuery({
    queryKey: ['sprint', sprintId],
    queryFn: () => api.getSprint(sprintId),
    enabled: Boolean(sprintId),
  })

  const projectId = sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? ''
  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', projectId, 'ui'],
    queryFn: () => api.getApiEnvironments(projectId, 'ui'),
    enabled: Boolean(projectId),
  })
  const uiEnvironments = useMemo(() => listItems(environmentsQuery.data), [environmentsQuery.data])
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState('')
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [missingVariables, setMissingVariables] = useState<UiMissingVariable[]>([])
  const [missingValues, setMissingValues] = useState<Record<string, string>>({})
  const [lastRunAction, setLastRunAction] = useState<'suite' | 'debug' | ''>('')
  const defaultEnvironmentId = useMemo(
    () => (uiEnvironments.find((item) => item.isDefault) ?? uiEnvironments[0])?.environmentId ?? '',
    [uiEnvironments],
  )
  const resolvedEnvironmentId = selectedEnvironmentId || defaultEnvironmentId
  const environmentVarsQuery = useQuery({
    queryKey: ['apiEnvironmentVars', resolvedEnvironmentId],
    queryFn: () => api.getApiEnvironmentVars(resolvedEnvironmentId),
    enabled: Boolean(resolvedEnvironmentId),
  })
  const environmentVars = useMemo(
    () => listItems(environmentVarsQuery.data),
    [environmentVarsQuery.data],
  )
  // baseUrl 不在变量表里，但它是 UI 运行内置变量，插入弹窗要和它一起展示。
  const pickerEnvironmentVars = useMemo(() => {
    const baseUrl = uiEnvironments.find((item) => item.environmentId === resolvedEnvironmentId)?.baseUrl?.trim()
    if (!baseUrl) return environmentVars
    return [
      {
        envVarId: '__builtin_base_url__',
        environmentId: resolvedEnvironmentId,
        varKey: 'baseUrl',
        value: baseUrl,
        description: '当前环境基础地址',
      },
      ...environmentVars,
    ]
  }, [environmentVars, resolvedEnvironmentId, uiEnvironments])
  const environmentOptions = useMemo(
    () =>
      uiEnvironments
        .map((item) => ({ label: item.name, value: item.environmentId ?? '' }))
        .filter((item) => item.value),
    [uiEnvironments],
  )
  const missingEnvironmentNames = useMemo(
    () =>
      Array.from(
        new Set(
          missingVariables
            .filter((item) => item.kind !== 'builtin' && item.name)
            .map((item) => String(item.name)),
        ),
      ),
    [missingVariables],
  )
  const hasMissingBuiltin = useMemo(
    () => missingVariables.some((item) => item.kind === 'builtin'),
    [missingVariables],
  )

  const { can } = useProjectAccess(sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? '')
  const casesQuery = useQuery({
    queryKey: ['uiTestCases', suiteId],
    queryFn: () => api.getUiTestCases(suiteId),
    enabled: Boolean(suiteId),
  })

  const uiTestCases = casesQuery.data ?? EMPTY_UI_TEST_CASES
  const activeCaseId = selectedCaseId && selectedCaseId !== DRAFT_CASE_ID ? selectedCaseId : ''
  const selectedCaseDetailQuery = useQuery({
    queryKey: ['uiTestCase', activeCaseId],
    queryFn: () => api.getUiTestCase(activeCaseId),
    enabled: Boolean(activeCaseId),
    refetchOnWindowFocus: false,
    // 列表接口返回的就是同一份完整用例（含 stepsJson），进入用例时直接复用；
    // 不再每次切换都发详情请求，避免“编辑器先卸载、等数据回来再重建”。
    staleTime: Number.POSITIVE_INFINITY,
  })
  const caseStatus = queryClient.getQueryData<UiTestCaseRun>(['uiTestCaseRun', selectedRunId])?.status
  const caseEventsConnected = useRunEvents('ui-case', selectedRunId, Boolean(selectedRunId) && selectedRunId !== liveUiRunId && getRunPollingInterval(caseStatus) !== false, () => {
    void refreshRunQuery(queryClient, ['uiTestCaseRun', selectedRunId])
  })
  const suiteEventsConnected = useRunEvents('ui-suite', activePollingSuiteRunId, Boolean(activePollingSuiteRunId), () => {
    void refreshRunQuery(queryClient, ['uiTestSuiteRun', activePollingSuiteRunId])
    void refreshRunQuery(queryClient, ['uiTestSuiteRunReport', activePollingSuiteRunId])
  })
  const reportStatus = queryClient.getQueryData<UiTestSuiteRunSummary>(['uiTestSuiteRunReport', selectedSuiteRunId])?.status
  const reportEventsConnected = useRunEvents('ui-suite', selectedSuiteRunId,
    suiteRunReportOpen && selectedSuiteRunId !== activePollingSuiteRunId && Boolean(selectedSuiteRunId) && getRunPollingInterval(reportStatus) !== false, () => {
      void refreshRunQuery(queryClient, ['uiTestSuiteRunReport', selectedSuiteRunId])
    })

  const uiTestCaseRunQuery = useQuery({
    queryKey: ['uiTestCaseRun', selectedRunId],
    queryFn: ({ signal }) => api.getUiTestCaseRun(selectedRunId, signal),
    enabled: Boolean(selectedRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestCaseRun | undefined
      return (caseEventsConnected || selectedRunId === liveUiRunId) ? false : getRunEventFallbackInterval(data?.status)
    },
  })
  useEffect(() => {
    const error = uiTestCaseRunQuery.error
    if (!selectedRunId || selectedRunId === liveUiRunId || !(error instanceof ApiError) || error.status !== 404) return
    const current = queryClient.getQueryData<UiTestCaseRun>(['uiTestCaseRun', selectedRunId])
    if (current?.status && getRunPollingInterval(current.status) === false) return
    queryClient.setQueryData<UiTestCaseRun>(['uiTestCaseRun', selectedRunId], current => ({
      ...current,
      runId: selectedRunId,
      status: 'error',
      success: false,
      errorMessage: '调试结果已清理，无法找回，请重新运行',
    }))
  }, [selectedRunId, liveUiRunId, queryClient, uiTestCaseRunQuery.error])

  // 顶栏的「上次运行」与运行记录条数都要用这份历史，所以它不再等抽屉打开才启用。
  const suiteRunHistoryQuery = useInfiniteQuery({
    queryKey: ['uiTestSuiteRuns', suiteId],
    queryFn: ({ pageParam }) =>
      api.getUiTestSuiteRuns(suiteId, { page: pageParam, pageSize: RUN_HISTORY_PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, page) => sum + listItems(page).length, 0)
      return loaded < listTotal(lastPage) ? allPages.length + 1 : undefined
    },
    enabled: Boolean(suiteId),
    refetchOnWindowFocus: false,
    refetchInterval: suiteRunHistoryOpen ? RUN_HISTORY_POLL_INTERVAL : false,
  })
  const refetchSuiteHistory = suiteRunHistoryQuery.refetch
  useEffect(() => {
    if (suiteRunHistoryOpen) void refetchSuiteHistory({ cancelRefetch: false })
  }, [refetchSuiteHistory, suiteRunHistoryOpen])
  const activeSuiteRunQuery = useQuery({
    queryKey: ['uiTestSuiteRun', activePollingSuiteRunId],
    queryFn: ({ signal }) => api.getUiTestSuiteRun(activePollingSuiteRunId, signal),
    enabled: Boolean(activePollingSuiteRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestSuiteRunSummary | undefined
      return suiteEventsConnected ? false : getRunEventFallbackInterval(data?.status)
    },
  })
  // 画布即使在报告关闭时也需要用例和步骤的实时执行状态。
  const activeSuiteReportQuery = useQuery({
    queryKey: ['uiTestSuiteRunReport', activePollingSuiteRunId],
    queryFn: ({ signal }) => api.getUiTestSuiteRunReport(activePollingSuiteRunId, signal),
    enabled: Boolean(activePollingSuiteRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => suiteEventsConnected ? false : getRunEventFallbackInterval(query.state.data?.status),
  })
  const suiteRunReportQuery = useQuery({
    queryKey: ['uiTestSuiteRunReport', selectedSuiteRunId],
    queryFn: ({ signal }) => api.getUiTestSuiteRunReport(selectedSuiteRunId, signal),
    enabled: suiteRunReportOpen && Boolean(selectedSuiteRunId),
    refetchOnWindowFocus: false,
    // 用例级进度靠报告明细轮询：打开期间与运行摘要同节奏刷新，终态自动停止。
    refetchInterval: (query) => (reportEventsConnected || (selectedSuiteRunId === activePollingSuiteRunId && suiteEventsConnected))
      ? false : getRunEventFallbackInterval(query.state.data?.status),
  })

  const polledSuiteRunSummary = activeSuiteRunQuery.data?.suiteRunId === selectedSuiteRunId
    ? activeSuiteRunQuery.data
    : suiteRunHistoryQuery.data?.pages
        .flatMap((page) => listItems(page))
        .find((run) => run.suiteRunId === selectedSuiteRunId)
  useRunReportRefresh({
    queryKey: 'uiTestSuiteRunReport', runId: selectedSuiteRunId, open: suiteRunReportOpen,
    status: polledSuiteRunSummary?.status, reportStatus: suiteRunReportQuery.data?.status,
  })

  const isCreatingCase = selectedCaseId === DRAFT_CASE_ID
  const watchedSteps = Form.useWatch('steps', { form: caseForm, preserve: true }) ?? []
  const watchedEnabled = Form.useWatch('enabled', { form: caseForm, preserve: true }) ?? false

  function getCompleteCaseFormValues() {
    const allValues = caseForm.getFieldsValue(true) as Partial<UiTestCaseFormValues>
    return {
      ...createDefaultUiTestCaseFormValues(),
      ...allValues,
      steps: allValues.steps ?? [],
    } satisfies UiTestCaseFormValues
  }

  function syncCaseDetailState(nextCase: UiTestCase) {
    const caseId = normalizeUiTestCaseId(nextCase)
    if (!caseId) return

    setEditingCase(nextCase)
    setSelectedCaseId(caseId)
    setCaseDirty(false)
    caseForm.setFieldsValue(buildUiTestCaseFormValues(nextCase))
    queryClient.setQueryData(['uiTestCase', caseId], nextCase)
  }

  function toggleStepPanel(index: number) {
    setExpandedStepIndexes((current) => (current.includes(index) ? current.filter((item) => item !== index) : [...current, index]))
  }

  // 流程末尾的“+”卡片把步骤追加到当前用例，右侧步骤配置负责填写内容。
  function addStep() {
    const steps = ((caseForm.getFieldValue('steps') as UiTestStepFormValue[] | undefined) ?? []).filter(Boolean)
    const nextSteps = [...steps, { enabled: true, continueOnFailure: false }]
    caseForm.setFieldsValue({ steps: nextSteps })
    caseForm.setFields([{ name: 'steps', touched: true }])
    setCaseDirty(true)
    const nextIndex = nextSteps.length - 1
    setSelectedStepIndex(nextIndex)
    setExpandedStepIndexes([nextIndex])
    if (isCreatingCase) {
      setDraftCaseValues((current) => (current ? { ...current, steps: nextSteps } : current))
    }
  }

  function removeStep(remove: (index: number | number[]) => void, index: number) {
    remove(index)
    setCaseDirty(true)
    const nextIndex = Math.max(0, Math.min(index, watchedSteps.length - 2))
    setSelectedStepIndex(nextIndex)
    setExpandedStepIndexes([nextIndex])
  }

  function moveStep(move: (from: number, to: number) => void, fromIndex: number, toIndex: number) {
    move(fromIndex, toIndex)
    setCaseDirty(true)
    setExpandedStepIndexes((current) => current.map((item) => moveExpandedStepIndex(item, fromIndex, toIndex)))
  }

  function handleStepDragStart(event: DragEvent<HTMLDivElement>, index: number) {
    setDraggingStepIndex(index)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(index))
  }

  function handleStepDrop(move: (from: number, to: number) => void, targetIndex: number) {
    if (draggingStepIndex === null || draggingStepIndex === targetIndex) return

    moveStep(move, draggingStepIndex, targetIndex)
    setDraggingStepIndex(null)
  }

  function getTemplateRefKey(stepIndex: number, fieldKey: UiTemplateFieldKey) {
    return `${stepIndex}:${fieldKey}`
  }

  function bindTemplateInputRef(stepIndex: number, fieldKey: UiTemplateFieldKey) {
    return (instance: InputRef | null) => {
      templateInputRefs.current[getTemplateRefKey(stepIndex, fieldKey)] = instance
    }
  }

  // XPath 定位里的变量必须带 |xpath，插入时直接生成执行器能用的形式。
  const templatePickerStep = templatePickerTarget
    ? watchedSteps[templatePickerTarget.stepIndex]
    : undefined
  const templatePickerUsesXpath =
    templatePickerTarget?.fieldKey === 'locatorValue' && templatePickerStep?.locatorType === 'xpath'

  function formatEnvironmentTokenForTarget(name: string) {
    if (name === 'baseUrl') return '{{baseUrl}}'
    return templatePickerUsesXpath ? `{{${name}|xpath}}` : `{{${name}}}`
  }

  function insertTemplateToken(stepIndex: number, fieldKey: UiTemplateFieldKey, token: string) {
    const path: ['steps', number, UiTemplateFieldKey] = ['steps', stepIndex, fieldKey]
    const currentValue = (caseForm.getFieldValue(path) as string | undefined) ?? ''
    const inputRef = templateInputRefs.current[getTemplateRefKey(stepIndex, fieldKey)]
    const inputElement = inputRef?.input ?? null

    if (!inputElement) {
      caseForm.setFieldValue(path, `${currentValue}${token}`)
      setTemplatePickerTarget(null)
      return
    }

    const selectionStart = inputElement.selectionStart ?? currentValue.length
    const selectionEnd = inputElement.selectionEnd ?? currentValue.length
    const nextValue = `${currentValue.slice(0, selectionStart)}${token}${currentValue.slice(selectionEnd)}`
    const nextCursor = selectionStart + token.length

    caseForm.setFieldValue(path, nextValue)
    setTemplatePickerTarget(null)

    requestAnimationFrame(() => {
      inputElement.focus()
      inputElement.setSelectionRange(nextCursor, nextCursor)
    })
  }

  function renderTemplatePickerLabel(stepIndex: number, fieldKey: UiTemplateFieldKey, label: string) {
    return (
      <div className="ui-template-picker-label inline-flex items-center gap-0">
        <span>{label}</span>
        <Button
          type="link"
          size="small"
          className="ui-template-picker-trigger h-auto whitespace-nowrap p-0 text-xs leading-[18px]"
          icon={<CodeOutlined />}
          onClick={() => setTemplatePickerTarget({ stepIndex, fieldKey })}
        >
          插入变量
        </Button>
      </div>
    )
  }

  const createCaseMutation = useMutation({
    mutationFn: (values: UiTestCaseFormValues) =>
      api.createUiTestCase(suiteId, (() => {
        const currentOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : sortUiTestCases(uiTestCases).map((item) => normalizeUiTestCaseId(item))).filter(Boolean)
        return {
          ...serializeUiTestCaseValues(values),
          orderNo: currentOrderIds.length + 1,
        }
      })()),
    onSuccess: (createdCase) => {
      const createdCaseId = normalizeUiTestCaseId(createdCase)
      const currentOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : sortUiTestCases(uiTestCases).map((item) => normalizeUiTestCaseId(item))).filter(Boolean)
      const nextOrderIds = [...currentOrderIds.filter((id) => id !== createdCaseId), createdCaseId]
      message.success('UI测试用例已创建')
      setDraftCaseValues(null)
      if (createdCaseId) {
        queryClient.setQueryData(['uiTestCase', createdCaseId], createdCase)
      }
      syncCaseDetailState(createdCase)
      caseOrderRollbackRef.current = caseOrderIds
      setCaseOrderIds(nextOrderIds)
      reorderCasesMutation.mutate(nextOrderIds)
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
  })

  const updateCaseMutation = useMutation({
    mutationFn: (values: UiTestCaseFormValues) => {
      const payload = buildUiTestCaseUpdatePayload(editingCase!, {
        name: values.name,
        enabled: values.enabled,
        orderNo: editingCase?.orderNo,
        stepsJson: serializeSteps(values.steps),
      })

      if (Object.keys(payload).length === 0) {
        return Promise.resolve(editingCase!)
      }

      return api.updateUiTestCase(activeCaseId, payload)
    },
    onSuccess: (updatedCase) => {
      message.success('UI测试用例已更新')
      syncCaseDetailState(updatedCase)
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deleteUiTestCase(caseId),
    onSuccess: (_, caseId) => {
      message.success('UI测试用例已删除')
      setCaseOrderIds((current) => current.filter((id) => id !== caseId))
      if (selectedCaseId === caseId) {
        setSelectedCaseId('')
        setEditingCase(null)
        setCaseDirty(false)
        caseForm.setFieldsValue(createDefaultUiTestCaseFormValues())
      }
      queryClient.removeQueries({ queryKey: ['uiTestCase', caseId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const debugRunMutation = useMutation({
    mutationFn: async () => {
      if (!activeCaseId) {
        throw new Error('未选择可运行的 UI测试用例')
      }
      if (!resolvedEnvironmentId) {
        throw new Error('请先选择 UI 环境')
      }

      const body = buildUiSuiteDebugRunPayload(resolvedEnvironmentId, suiteQuery.data)
      let runId = ''
      try {
        const stream = await startDebugStream<UiTestCaseRun>('ui-case', activeCaseId, body, (event) => {
          if (event.type === 'changed') {
            void queryClient.invalidateQueries({ queryKey: ['uiTestCaseRun', runId] })
          } else if (event.type === 'execution_finished') {
            const { status } = event.data as Pick<UiTestCaseRun, 'status'>
            void queryClient.cancelQueries({ queryKey: ['uiTestCaseRun', runId], exact: true })
            queryClient.setQueryData<UiTestCaseRun>(['uiTestCaseRun', runId], current => ({
              ...current,
              runId,
              status,
              success: status === 'success',
            }))
          } else if (event.type === 'finished') {
            const result = event.data as UiTestCaseRun
            // A request begun before this event must not replace the final result.
            void queryClient.cancelQueries({ queryKey: ['uiTestCaseRun', runId], exact: true })
            queryClient.setQueryData(['uiTestCaseRun', runId], result)
            setLiveUiRunId('')
            if (result.status === 'success') message.success('调试运行完成')
            else if (result.status === 'canceled') message.info('调试运行已停止')
            else message.error(result.errorMessage || '调试运行完成，存在失败项')
          } else if (event.type === 'disconnected') {
            setLiveUiRunId('')
            message.warning('实时连接已断开，结果可能无法找回')
          }
        })
        runId = getUiTestCaseRunId(stream.initial)
        return { runRecord: stream.initial, stream }
      } catch (error) {
        if (!(error instanceof DebugStreamUnavailable)) throw error
        message.warning('实时连接不可用，结果可能无法找回')
        return { runRecord: await api.debugRunUiTestCase(activeCaseId, { ...body, liveDebug: true }), stream: null }
      }
    },
    onError: handleRunError,
    onSuccess: ({ runRecord, stream }) => {
      debugStreamRef.current?.abort()
      debugStreamRef.current = stream
      const runId = getUiTestCaseRunId(runRecord)
      if (!runId) {
        message.error('未获取到运行记录 ID')
        return
      }

      queryClient.setQueryData(['uiTestCaseRun', runId], runRecord)
      setSelectedRunId(runId)
      setLiveUiRunId(stream ? runId : '')
      message.success(isUiRunPollingStatus(runRecord.status) ? '已开始调试运行' : '调试运行记录已创建')
      stream?.activate()
    },
  })
  const runSuiteMutation = useMutation({
    mutationFn: () => {
      if (!suiteId) {
        throw new Error('未找到可运行的 UI测试集')
      }
      if (!resolvedEnvironmentId) {
        throw new Error('请先选择 UI 环境')
      }

      return api.runUiTestSuite(
        suiteId,
        buildUiSuiteRunPayload(resolvedEnvironmentId, suiteQuery.data),
      )
    },
    onError: handleRunError,
    onSuccess: (runRecord) => {
      const suiteRunId = getUiTestSuiteRunId(runRecord)
      if (!suiteRunId) {
        message.error('未获取到运行记录 ID')
        return
      }

      queryClient.invalidateQueries({ queryKey: ['uiTestSuiteRuns', suiteId] })
      void refetchSuiteHistory()

      setSelectedSuiteRunId(suiteRunId)
      setActivePollingSuiteRunId(suiteRunId)
      setSuiteRunReportOpen(true)
      setSuiteRunHistoryOpen(false)
      setLoadingSuiteRunHistoryId('')
      setSearchParams({ suiteRunId }, { replace: true })
      message.success(isUiRunPollingStatus(runRecord.status) ? '已开始运行测试集' : '测试集运行记录已创建')
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['uiTestSuiteRuns', suiteId] })
    },
  })

  const saveMissingVariablesMutation = useMutation({
    mutationFn: async () => {
      if (!resolvedEnvironmentId) {
        throw new Error('请先选择 UI 环境')
      }
      for (const name of missingEnvironmentNames) {
        const value = missingValues[name]
        if (value === undefined) {
          throw new Error(`请填写变量 ${name}`)
        }
        await api.createApiEnvironmentVar(resolvedEnvironmentId, { varKey: name, value })
      }
    },
    onSuccess: () => {
      message.success('变量已补充，正在重新校验')
      setMissingVariables([])
      setMissingValues({})
      queryClient.invalidateQueries({ queryKey: ['testEnvironments', projectId, 'ui'] })
      if (resolvedEnvironmentId) {
        queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', resolvedEnvironmentId] })
      }
      if (lastRunAction === 'suite') {
        runSuiteMutation.mutate()
      } else if (lastRunAction === 'debug') {
        debugRunMutation.mutate()
      }
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const reorderCasesMutation = useMutation({
    mutationFn: async (nextOrderIds: string[]) => {
      const caseMap = new Map(uiTestCases.map((item) => [normalizeUiTestCaseId(item), item]))

      await Promise.all(
        nextOrderIds.map((caseId, index) => {
          const targetCase = caseMap.get(caseId)
          const nextOrderNo = index + 1

          if (targetCase?.orderNo === nextOrderNo) return Promise.resolve()
          return api.updateUiTestCase(caseId, { orderNo: nextOrderNo })
        }),
      )
    },
    onSuccess: () => {
      message.success('用例顺序已更新')
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
    onError: (error) => {
      setCaseOrderIds(caseOrderRollbackRef.current)
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      caseOrderRollbackRef.current = []
    },
  })

  const importUiCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) => api.importUiTestCases(suiteId, file, filename),
    onSuccess: (result) => {
      const importedCaseCount = result.importedCaseCount ?? result.imported ?? 0
      message.success(`导入成功：${importedCaseCount} 条用例，${result.importedStepCount ?? 0} 个步骤`)
      setCaseImportModalOpen(false)
      setCaseImportMode('upload')
      setImportYamlFile(null)
      setImportYamlText('')
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
    onError: (error) => {
      message.error(getErrorMessage(error))
    },
  })

  const draftCase = useMemo<UiTestCase | null>(
    () =>
      draftCaseValues
        ? {
          caseId: DRAFT_CASE_ID,
          name: draftCaseValues.name?.trim() || '未保存用例',
          enabled: draftCaseValues.enabled,
          stepsJson: serializeSteps(draftCaseValues.steps),
        }
        : null,
    [draftCaseValues],
  )

  const orderedCases = useMemo(() => {
    const byRule = sortUiTestCases(uiTestCases)
    if (caseOrderIds.length === 0) return byRule

    const caseMap = new Map(byRule.map((item) => [normalizeUiTestCaseId(item), item]))
    const ordered = caseOrderIds.map((caseId) => caseMap.get(caseId)).filter(Boolean) as UiTestCase[]
    const missing = byRule.filter((item) => !caseOrderIds.includes(normalizeUiTestCaseId(item)))
    return [...ordered, ...missing]
  }, [caseOrderIds, uiTestCases])

  const caseList = useMemo(() => (draftCase ? [...orderedCases, draftCase] : orderedCases), [draftCase, orderedCases])
  const canReorder = can('write')

  const suiteRunHistory = useMemo(
    () =>
      (suiteRunHistoryQuery.data?.pages.flatMap((page) => listItems(page)) ?? []).sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [suiteRunHistoryQuery.data],
  )
  const suiteRunHistoryTotal = suiteRunHistoryQuery.data?.pages[0]
    ? listTotal(suiteRunHistoryQuery.data.pages[0])
    : 0
  const latestSuiteRun = useMemo(
    () =>
      (activeSuiteRunQuery.data?.suiteRunId === selectedSuiteRunId ? activeSuiteRunQuery.data : undefined) ??
      suiteRunHistory[0] ??
      null,
    [activeSuiteRunQuery.data, selectedSuiteRunId, suiteRunHistory],
  )
  const readiness = useMemo(() => getUiSuiteReadiness(latestSuiteRun), [latestSuiteRun])

  const selectedSuiteRunSummary = useMemo(
    () => polledSuiteRunSummary ?? null,
    [polledSuiteRunSummary],
  )
  const suiteRunReport = suiteRunReportQuery.data
    ? { ...suiteRunReportQuery.data, ...(isUiRunPollingStatus(suiteRunReportQuery.data.status) ? selectedSuiteRunSummary : undefined) }
    : null
  const orderedSuiteRunItems = useMemo(
    () =>
      [...(suiteRunReport?.items ?? [])].sort(
        (left, right) =>
          compareByOrderNo(left, right) ||
          (left.caseName ?? '').localeCompare(right.caseName ?? ''),
      ),
    [suiteRunReport?.items],
  )

  const currentRun = uiTestCaseRunQuery.data ?? null
  // 步骤卡片上的 PASS / FAIL 徽标取自最近一次调试运行，按顺序号对齐当前用例的步骤。
  const currentRunStepResults = useMemo(
    () => [...(currentRun?.stepResults ?? [])],
    [currentRun?.stepResults],
  )
  const caseSerial = formatUiCaseSerial(editingCase?.orderNo ?? (isCreatingCase ? undefined : orderedCases.findIndex((item) => normalizeUiTestCaseId(item) === activeCaseId) + 1))
  const screenshotText = formatUiScreenshotPolicy(suiteQuery.data?.screenshotPolicy)

  useEffect(() => {
    setSelectedCaseId('')
    setFlowLevel('cases')
    setDraftCaseValues(null)
    setEditingCase(null)
    setExpandedStepIndexes([])
    setDraggingStepIndex(null)
    setSelectedRunId('')
    setSuiteRunHistoryOpen(false)
    setSuiteRunReportOpen(false)
    setSelectedSuiteRunId('')
    setActivePollingSuiteRunId('')
    setLoadingSuiteRunHistoryId('')
    setRefreshingSuiteRunReport(false)
    setSuiteRunReportView('items')
    setExpandedSuiteRunItemIds([])
    setCaseImportModalOpen(false)
    setCaseImportMode('upload')
    setImportYamlFile(null)
    setImportYamlText('')
    setTemplatePickerTarget(null)
    caseForm.setFieldsValue(createDefaultUiTestCaseFormValues())
  }, [caseForm, suiteId])

  useEffect(() => {
    const nextSuiteRunId = searchParams.get('suiteRunId') ?? ''
    if (!nextSuiteRunId) return

    setSelectedSuiteRunId((current) => (current === nextSuiteRunId ? current : nextSuiteRunId))
    setActivePollingSuiteRunId(nextSuiteRunId)
    setSuiteRunReportOpen(true)
  }, [searchParams])

  useEffect(() => {
    setSelectedStepIndex(0)
    setExpandedStepIndexes([0])
    setDraggingStepIndex(null)
    setSelectedRunId('')
    setCaseDirty(false)
  }, [selectedCaseId])

  useEffect(() => {
    const currentSuiteRun = activeSuiteRunQuery.data
    if (!currentSuiteRun?.suiteRunId) return

    if (!isUiRunPollingStatus(currentSuiteRun.status)) {
      setActivePollingSuiteRunId((current) => (current === currentSuiteRun.suiteRunId ? '' : current))
      queryClient.invalidateQueries({ queryKey: ['uiTestSuiteRuns', suiteId] })
    }
  }, [activeSuiteRunQuery.data, queryClient, suiteId])

  useEffect(() => {
    if (!selectedSuiteRunId) {
      if (loadingSuiteRunHistoryId) setLoadingSuiteRunHistoryId('')
      return
    }

    if (suiteRunReportQuery.isFetching) return
    if (loadingSuiteRunHistoryId === selectedSuiteRunId) {
      setLoadingSuiteRunHistoryId('')
    }
  }, [loadingSuiteRunHistoryId, selectedSuiteRunId, suiteRunReportQuery.isFetching])

  useEffect(() => {
    setSuiteRunReportView('items')
    setExpandedSuiteRunItemIds([])
  }, [suiteRunReportQuery.data?.suiteRunId])

  useEffect(() => {
    if (selectedCaseId !== DRAFT_CASE_ID) return

    setEditingCase(null)
    caseForm.setFieldsValue(draftCaseValues ?? createDefaultUiTestCaseFormValues())
  }, [caseForm, draftCaseValues, selectedCaseId, uiTestCases])

  // 列表接口已经带回每个用例的完整步骤，先预热详情缓存；
  // 这样进入用例时详情查询直接命中缓存，不需要额外的网络往返。
  useLayoutEffect(() => {
    if (uiTestCases.length === 0) return

    for (const item of uiTestCases) {
      const caseId = normalizeUiTestCaseId(item)
      if (!caseId || queryClient.getQueryData(['uiTestCase', caseId])) continue
      queryClient.setQueryData(['uiTestCase', caseId], item)
    }
  }, [queryClient, uiTestCases])

  // 查询数据同步到编辑态必须发生在绘制前，否则会先闪一帧“未找到”或空表单。
  useLayoutEffect(() => {
    if (!activeCaseId || !selectedCaseDetailQuery.data) return
    // 点击卡片时已经用列表数据同步过编辑态，这里不再覆盖，避免多一次整树渲染。
    if (editingCase && normalizeUiTestCaseId(editingCase) === activeCaseId) return

    setEditingCase(selectedCaseDetailQuery.data)
    caseForm.setFieldsValue(buildUiTestCaseFormValues(selectedCaseDetailQuery.data))
  }, [activeCaseId, caseForm, editingCase, selectedCaseDetailQuery.data])

  useEffect(() => {
    if (reorderCasesMutation.isPending) return

    const nextIds = sortUiTestCases(uiTestCases)
      .map((item) => normalizeUiTestCaseId(item))
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
  }, [reorderCasesMutation.isPending, uiTestCases])

  // 用例列表到达后立刻补上默认选中，避免首帧落到“未找到”兜底。
  useLayoutEffect(() => {
    if (caseList.length === 0) {
      if (selectedCaseId) {
        setSelectedCaseId('')
        setEditingCase(null)
      }
      return
    }

    const exists = caseList.some((item) => normalizeUiTestCaseId(item) === selectedCaseId)
    if (!selectedCaseId || !exists) {
      setSelectedCaseId(normalizeUiTestCaseId(caseList[0]))
    }
  }, [caseList, selectedCaseId])

  function openCreateCase() {
    setFlowLevel('steps')
    const nextDraft = draftCaseValues ?? createDefaultUiTestCaseFormValues()
    setDraftCaseValues(nextDraft)
    setSelectedCaseId(DRAFT_CASE_ID)
    setEditingCase(null)
    setCaseDirty(true)
    setSelectedStepIndex(0)
    setExpandedStepIndexes([])
    caseForm.setFieldsValue(nextDraft)
  }

  function handleRunError(error: Error) {
    if (error instanceof ApiError) {
      const missing = (error.data as { missingVariables?: UiMissingVariable[] } | undefined)
        ?.missingVariables
      if (missing?.length) {
        setMissingVariables(missing)
        setMissingValues({})
        return
      }
    }
    message.error(getErrorMessage(error))
  }

  function closeMissingVariablesModal() {
    setMissingVariables([])
    setMissingValues({})
  }

  function handleDebugRun() {
    if (!activeCaseId || isCreatingCase) return
    if (!resolvedEnvironmentId) {
      message.warning('请先选择 UI 环境')
      return
    }

    if (hasUnsavedCaseChanges) {
      message.warning('当前页面还有未保存修改，调试运行会基于最近一次保存的用例内容。')
    }

    setLastRunAction('debug')
    debugRunMutation.mutate()
  }

  function handleRunSuite() {
    if (!suiteId || uiTestCases.length === 0) return
    if (!resolvedEnvironmentId) {
      message.warning('请先选择 UI 环境')
      return
    }

    if (hasUnsavedCaseChanges) {
      message.warning('当前页面还有未保存修改，正式运行会基于最近一次保存的用例内容。')
    }

    setLastRunAction('suite')
    runSuiteMutation.mutate()
  }

  function handleOpenSuiteRunHistoryItem(runSummary: UiTestSuiteRunSummary) {
    const suiteRunId = getUiTestSuiteRunId(runSummary)
    setLoadingSuiteRunHistoryId(suiteRunId)
    setSelectedSuiteRunId(suiteRunId)
    setSuiteRunReportOpen(true)
    setSuiteRunHistoryOpen(false)
    if (isUiRunPollingStatus(runSummary.status) && suiteRunId) {
      setActivePollingSuiteRunId(suiteRunId)
    }
    if (suiteRunId) {
      setSearchParams({ suiteRunId }, { replace: true })
    }
  }

  function closeSuiteRunReport() {
    setSuiteRunReportOpen(false)
    setSelectedSuiteRunId('')
    setLoadingSuiteRunHistoryId('')
    setSearchParams({}, { replace: true })
  }

  function toggleSuiteRunItem(itemKey: string) {
    setExpandedSuiteRunItemIds((current) => (current.includes(itemKey) ? current.filter((item) => item !== itemKey) : [...current, itemKey]))
  }

  async function handleRefreshSuiteRunReport() {
    if (!selectedSuiteRunId) return

    setRefreshingSuiteRunReport(true)
    try {
      await suiteRunReportQuery.refetch()
      await queryClient.invalidateQueries({ queryKey: ['uiTestSuiteRun', selectedSuiteRunId] })
      await queryClient.invalidateQueries({ queryKey: ['uiTestSuiteRuns', suiteId] })
      message.success('报告已刷新')
    } finally {
      setRefreshingSuiteRunReport(false)
    }
  }

  function handleDiscardDraft() {
    setDraftCaseValues(null)
    setCaseDirty(false)
    const fallbackCase = orderedCases[0] ?? null
    if (fallbackCase) {
      setSelectedCaseId(normalizeUiTestCaseId(fallbackCase))
      return
    }

    setSelectedCaseId('')
    setEditingCase(null)
    caseForm.setFieldsValue(createDefaultUiTestCaseFormValues())
  }

  function handleSelectCase(caseId: string) {
    setFlowLevel('steps')
    setTemplatePickerTarget(null)
    // 列表里已经有完整步骤，立即切换编辑态：不卸载编辑器，也不等详情请求。
    if (caseId !== DRAFT_CASE_ID) {
      const nextCase = queryClient.getQueryData<UiTestCase>(['uiTestCase', caseId])
        ?? orderedCases.find((item) => normalizeUiTestCaseId(item) === caseId)
      if (nextCase) {
        if (!queryClient.getQueryData(['uiTestCase', caseId])) {
          queryClient.setQueryData(['uiTestCase', caseId], nextCase)
        }
        setEditingCase(nextCase)
        caseForm.setFieldsValue(buildUiTestCaseFormValues(nextCase))
        setCaseDirty(false)
      }
    }
    if (caseId !== selectedCaseId) {
      setSelectedStepIndex(0)
      setExpandedStepIndexes([])
    }
    setSelectedCaseId(caseId)
  }

  function confirmDeleteCase(caseId: string, caseName: string) {
    if (!caseId) return
    Modal.confirm({
      title: '删除 UI 测试用例',
      content: `确认删除“${caseName || '未命名用例'}”？删除后不可恢复。`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => {
        deleteCaseMutation.mutate(caseId)
      },
    })
  }

  async function handleRefreshUiRunDetail() {
    if (!selectedRunId) return
    await uiTestCaseRunQuery.refetch()
  }

  function openCaseImportModal() {
    setCaseImportModalOpen(true)
  }

  function closeCaseImportModal() {
    if (importUiCasesMutation.isPending) return
    setCaseImportModalOpen(false)
    setCaseImportMode('upload')
    setImportYamlFile(null)
    setImportYamlText('')
  }

  function handleImportUiCases() {
    if (!suiteId) return

    if (caseImportMode === 'upload') {
      if (!importYamlFile) {
        message.warning('请上传 YAML 文件')
        return
      }
      if (!isYamlFileName(importYamlFile.name)) {
        message.warning('仅支持 .yaml 或 .yml 文件')
        return
      }

      importUiCasesMutation.mutate({
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

    const generatedFileName = `ui-suite-${suiteId || 'cases'}.yaml`
    importUiCasesMutation.mutate({
      file: new File([yamlContent], generatedFileName, { type: 'application/x-yaml' }),
      filename: generatedFileName,
    })
  }

  const showEditorForm = isCreatingCase || (Boolean(activeCaseId) && Boolean(editingCase) && normalizeUiTestCaseId(editingCase!) === activeCaseId)
  // 自动选中、详情请求以及数据同步到 editingCase 之间都有一帧空档；先占位，避免闪出“未找到”。
  const caseDetailLoading = !showEditorForm && (!activeCaseId || selectedCaseDetailQuery.isPending || Boolean(selectedCaseDetailQuery.data))
  const hasUnsavedCaseChanges = caseDirty
  const runningSuiteItems = activeSuiteReportQuery.data?.status === 'running' && activeSuiteRunQuery.data?.status === 'running'
    ? activeSuiteReportQuery.data.items ?? [] : []
  const runningCaseIds = runningSuiteItems.filter((item) => item.status === 'running' && item.caseId).map((item) => item.caseId!)
  const runningSuiteCase = runningSuiteItems.find((item) => item.caseId === activeCaseId && item.status === 'running')
  const runningStepResults = runningSuiteCase?.stepResults ?? (currentRun?.status === 'running' ? currentRun.stepResults : undefined) ?? []
  const runningStepIds = runningStepResults.filter((step) => step.status === 'running' && typeof step.orderNo === 'number' && step.orderNo > 0).map((step) => String(step.orderNo! - 1))
  const caseFlowItems: FlowItem[] = orderedCases.map((item, index) => {
    const caseId = normalizeUiTestCaseId(item)
    return {
      id: caseId,
      title: item.name || '未命名用例',
      serial: formatUiCaseSerial(index + 1),
      caption: `${getUiTestCaseStepCount(item)} 个步骤 · 点击进入`,
      enabled: item.enabled !== false,
      actions: can('write') ? [
        { key: 'open', label: '打开用例', onSelect: () => handleSelectCase(caseId) },
        { key: 'delete', label: '删除用例', danger: true, onSelect: () => confirmDeleteCase(caseId, item.name) },
      ] : undefined,
    }
  })
  if (draftCase) {
    caseFlowItems.push({
      id: DRAFT_CASE_ID, title: draftCase.name || '未保存用例', serial: formatUiCaseSerial(orderedCases.length + 1),
      caption: `${getUiTestCaseStepCount(draftCase)} 个步骤 · 未保存草稿`, enabled: draftCase.enabled !== false,
      actions: can('write') ? [{ key: 'discard', label: '丢弃草稿', danger: true, onSelect: handleDiscardDraft }] : undefined,
    })
  }
  const stepFlowItems: FlowItem[] = watchedSteps.map((step, index) => ({
    id: String(index), title: step?.stepName || '未命名步骤', serial: `#${index + 1}`,
    caption: [step?.keyword, step?.locatorType].filter(Boolean).join(' · ') || '待配置', enabled: step?.enabled !== false,
    result: currentRunStepResults.find((result) => result.orderNo === index + 1),
  }))
  function applyCaseFlowOrder(order: string[]) {
    if (!canReorder || reorderCasesMutation.isPending) return
    // 草稿卡片只存在于前端，排序接口只接收已保存的用例。
    const savedOrder = order.filter((caseId) => caseId !== DRAFT_CASE_ID)
    caseOrderRollbackRef.current = caseOrderIds
    setCaseOrderIds(savedOrder)
    if (savedOrder.length > 0) reorderCasesMutation.mutate(savedOrder)
  }
  function applyStepFlowOrder(order: string[]) {
    if (!can('write')) return
    const steps = caseForm.getFieldValue('steps') as UiTestStepFormValue[] | undefined
    if (!steps || order.length !== steps.length) return
    const nextSteps = order.map((id) => steps[Number(id)])
    if (nextSteps.some((step) => !step)) return
    caseForm.setFieldsValue({ steps: nextSteps })
    caseForm.setFields([{ name: 'steps', touched: true }])
    setCaseDirty(true)
    if (isCreatingCase) setDraftCaseValues((current) => current ? { ...current, steps: nextSteps } : current)
    const nextSelectedIndex = order.indexOf(String(selectedStepIndex))
    setSelectedStepIndex(Math.max(0, nextSelectedIndex))
    setExpandedStepIndexes([Math.max(0, nextSelectedIndex)])
  }
  function handleCaseSave() {
    if (flowLevel === 'cases' && caseFlowRef.current) {
      if (!caseFlowRef.current.prepareSave()) message.warning('请先将用例连线连接成完整的执行顺序，再保存')
      return
    }
    if (flowLevel === 'steps' && stepFlowRef.current && !stepFlowRef.current.prepareSave()) {
      message.warning('请先将步骤连线连接成完整的执行顺序，再保存用例')
      return
    }
    caseForm.submit()
  }
  const lastRunText = formatUiRunRelativeTime(latestSuiteRun?.startedAt || latestSuiteRun?.createdAt || latestSuiteRun?.updatedAt)
  return {
    navigate,
    queryClient,
    searchParams,
    setSearchParams,
    suiteId,
    selectedCaseId,
    setSelectedCaseId,
    caseDirty,
    setCaseDirty,
    stepFlowRef,
    caseFlowRef,
    flowLevel,
    setFlowLevel,
    selectedStepIndex,
    setSelectedStepIndex,
    stepConfigHost,
    setStepConfigHost,
    stepConfigTab,
    setStepConfigTab,
    draftCaseValues,
    setDraftCaseValues,
    editingCase,
    setEditingCase,
    caseOrderIds,
    setCaseOrderIds,
    expandedStepIndexes,
    setExpandedStepIndexes,
    draggingStepIndex,
    setDraggingStepIndex,
    selectedRunId,
    setSelectedRunId,
    liveUiRunId,
    setLiveUiRunId,
    debugStreamRef,
    suiteRunHistoryOpen,
    setSuiteRunHistoryOpen,
    suiteRunReportOpen,
    setSuiteRunReportOpen,
    selectedSuiteRunId,
    setSelectedSuiteRunId,
    activePollingSuiteRunId,
    setActivePollingSuiteRunId,
    loadingSuiteRunHistoryId,
    setLoadingSuiteRunHistoryId,
    refreshingSuiteRunReport,
    setRefreshingSuiteRunReport,
    suiteRunReportView,
    setSuiteRunReportView,
    expandedSuiteRunItemIds,
    setExpandedSuiteRunItemIds,
    caseImportModalOpen,
    setCaseImportModalOpen,
    caseImportMode,
    setCaseImportMode,
    importYamlFile,
    setImportYamlFile,
    importYamlText,
    setImportYamlText,
    templatePickerTarget,
    setTemplatePickerTarget,
    caseForm,
    caseOrderRollbackRef,
    templateInputRefs,
    suiteQuery,
    requirementId,
    requirementQuery,
    sprintId,
    sprintQuery,
    projectId,
    environmentsQuery,
    uiEnvironments,
    selectedEnvironmentId,
    setSelectedEnvironmentId,
    environmentDrawerOpen,
    setEnvironmentDrawerOpen,
    missingVariables,
    setMissingVariables,
    missingValues,
    setMissingValues,
    lastRunAction,
    setLastRunAction,
    defaultEnvironmentId,
    resolvedEnvironmentId,
    environmentVarsQuery,
    environmentVars,
    pickerEnvironmentVars,
    environmentOptions,
    missingEnvironmentNames,
    hasMissingBuiltin,
    can,
    casesQuery,
    uiTestCases,
    activeCaseId,
    selectedCaseDetailQuery,
    caseStatus,
    caseEventsConnected,
    suiteEventsConnected,
    reportStatus,
    reportEventsConnected,
    uiTestCaseRunQuery,
    suiteRunHistoryQuery,
    refetchSuiteHistory,
    activeSuiteRunQuery,
    activeSuiteReportQuery,
    suiteRunReportQuery,
    polledSuiteRunSummary,
    isCreatingCase,
    watchedSteps,
    watchedEnabled,
    getCompleteCaseFormValues,
    syncCaseDetailState,
    toggleStepPanel,
    addStep,
    removeStep,
    moveStep,
    handleStepDragStart,
    handleStepDrop,
    getTemplateRefKey,
    bindTemplateInputRef,
    templatePickerStep,
    templatePickerUsesXpath,
    formatEnvironmentTokenForTarget,
    insertTemplateToken,
    renderTemplatePickerLabel,
    createCaseMutation,
    updateCaseMutation,
    deleteCaseMutation,
    debugRunMutation,
    runSuiteMutation,
    saveMissingVariablesMutation,
    reorderCasesMutation,
    importUiCasesMutation,
    draftCase,
    orderedCases,
    caseList,
    canReorder,
    suiteRunHistory,
    suiteRunHistoryTotal,
    latestSuiteRun,
    readiness,
    selectedSuiteRunSummary,
    suiteRunReport,
    orderedSuiteRunItems,
    currentRun,
    currentRunStepResults,
    caseSerial,
    screenshotText,
    openCreateCase,
    handleRunError,
    closeMissingVariablesModal,
    handleDebugRun,
    handleRunSuite,
    handleOpenSuiteRunHistoryItem,
    closeSuiteRunReport,
    toggleSuiteRunItem,
    handleRefreshSuiteRunReport,
    handleDiscardDraft,
    handleSelectCase,
    confirmDeleteCase,
    handleRefreshUiRunDetail,
    openCaseImportModal,
    closeCaseImportModal,
    handleImportUiCases,
    showEditorForm,
    caseDetailLoading,
    hasUnsavedCaseChanges,
    runningSuiteItems,
    runningCaseIds,
    runningSuiteCase,
    runningStepResults,
    runningStepIds,
    caseFlowItems,
    stepFlowItems,
    applyCaseFlowOrder,
    applyStepFlowOrder,
    handleCaseSave,
    lastRunText,
  } as const
}

export type UiTestSuiteCasePageModel = ReturnType<typeof useUiTestSuiteCasePage>
