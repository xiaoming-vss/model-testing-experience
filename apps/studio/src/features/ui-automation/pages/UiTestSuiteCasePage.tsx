import { Text, Title } from '@/features/ui-automation/utils/detailView'
import { UiCaseImportModal } from '@/features/ui-automation/components/UiCaseImportModal'
import { UiStepEditor } from '@/features/ui-automation/components/UiStepEditor'
import { UiSuiteRunHistory } from '@/features/ui-automation/components/UiSuiteRunHistory'
import { UiSuiteRunReport } from '@/features/ui-automation/components/UiSuiteRunReport'
import { EDITOR_SPLITTER_HEIGHT, MIN_EDITOR_RESULT_HEIGHT, MIN_EDITOR_TOP_HEIGHT, UI_TEMPLATE_FIELD_LABELS, isYamlFileName, type CaseImportMode, type UiTemplateFieldKey } from '@/features/ui-automation/utils/detailView'
import { renderUiRunStepResultList } from '@/features/ui-automation/utils/renderUiRunSteps'

import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import {
  api,
  listItems,
  type UiTestCase,
  type UiTestCaseRun,
  type UiTestSuiteRunReport,
  type UiTestSuiteRunSummary
} from '@/services/api'
import { ActionButton } from '@/shared/components/ActionButton'
import { uiBuiltinTemplateFunctions } from '@/shared/constants/templateFunctions'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage,
  normalizeUiTestCaseId
} from '@/utils/format'
import { buildUiTestCaseUpdatePayload } from '@/utils/updatePayload'
import { ArrowLeftOutlined, CodeOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InputRef } from 'antd'
import { Alert, Button, Card, Empty, Form, Input, Popconfirm, Popover, Segmented, Switch, Tag, Tooltip } from 'antd'
import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { UiTestPanelSplitter } from '../components/UiTestPanelSplitter'
import {
  uiTestRunViewOptions,
  type UiSuiteRunReportView,
  type UiTestRunView
} from '../config/stepConfig'
import { formatUiScreenshotPolicy } from '../constants/defaultRunConfig'
import {
  buildUiSuiteDebugRunPayload,
  buildUiSuiteRunPayload,
  getExecutionStatusMeta,
  getUiTestCaseRunId,
  getUiTestSuiteRunId,
  isUiRunPollingStatus
} from '../utils/runHelpers'
import {
  DRAFT_CASE_ID,
  EMPTY_UI_TEST_CASES,
  buildUiTestCaseFormValues,
  createDefaultUiTestCaseFormValues,
  formatOptionalMs,
  formatViewportText,
  getUiTestCaseStepCount,
  moveArrayItem,
  moveExpandedStepIndex,
  prettyPrintValue,
  serializeSteps,
  serializeUiTestCaseValues,
  sortUiTestCases,
  type UiTestCaseFormValues,
  type UiTestStepFormValue
} from '../utils/uiTestCaseEditor'
import { getNextEditorTopHeight } from '../utils/uiTestPanelResize'

export function UiTestSuiteCasePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { suiteId = '' } = useParams<{ suiteId: string }>()
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [caseSearch, setCaseSearch] = useState('')
  const [draftCaseValues, setDraftCaseValues] = useState<UiTestCaseFormValues | null>(null)
  const [editingCase, setEditingCase] = useState<UiTestCase | null>(null)
  const [caseOrderIds, setCaseOrderIds] = useState<string[]>([])
  const [draggingCaseId, setDraggingCaseId] = useState<string | null>(null)
  const [expandedStepIndexes, setExpandedStepIndexes] = useState<number[]>([])
  const [draggingStepIndex, setDraggingStepIndex] = useState<number | null>(null)
  const [selectedRunId, setSelectedRunId] = useState('')
  const [uiRunView, setUiRunView] = useState<UiTestRunView>('steps')
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
  const [templatePickerOpenKey, setTemplatePickerOpenKey] = useState<string | null>(null)
  const [editorTopHeight, setEditorTopHeight] = useState(520)
  const [caseForm] = Form.useForm<UiTestCaseFormValues>()
  const caseOrderRollbackRef = useRef<string[]>([])
  const templateInputRefs = useRef<Record<string, InputRef | null>>({})
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)

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
  })
  const uiTestCaseRunQuery = useQuery({
    queryKey: ['uiTestCaseRun', selectedRunId],
    queryFn: () => api.getUiTestCaseRun(selectedRunId),
    enabled: Boolean(selectedRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestCaseRun | undefined
      return isUiRunPollingStatus(data?.status) || (!data && Boolean(selectedRunId)) ? 2000 : false
    },
  })
  const suiteRunHistoryQuery = useQuery({
    queryKey: ['uiTestSuiteRuns', suiteId],
    queryFn: () => api.getUiTestSuiteRuns(suiteId),
    enabled: suiteRunHistoryOpen && Boolean(suiteId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestSuiteRunSummary[] | undefined
      return suiteRunHistoryOpen && (data ?? []).some((item) => isUiRunPollingStatus(item.status)) ? 3000 : false
    },
  })
  const activeSuiteRunQuery = useQuery({
    queryKey: ['uiTestSuiteRun', activePollingSuiteRunId],
    queryFn: () => api.getUiTestSuiteRun(activePollingSuiteRunId),
    enabled: Boolean(activePollingSuiteRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestSuiteRunSummary | undefined
      return isUiRunPollingStatus(data?.status) || (!data && Boolean(activePollingSuiteRunId)) ? 3000 : false
    },
  })
  const suiteRunReportQuery = useQuery({
    queryKey: ['uiTestSuiteRunReport', selectedSuiteRunId],
    queryFn: () => api.getUiTestSuiteRunReport(selectedSuiteRunId),
    enabled: suiteRunReportOpen && Boolean(selectedSuiteRunId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestSuiteRunReport | undefined
      return suiteRunReportOpen && (isUiRunPollingStatus(data?.status) || (!data && Boolean(selectedSuiteRunId))) ? 3000 : false
    },
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
    caseForm.setFieldsValue(buildUiTestCaseFormValues(nextCase))
    queryClient.setQueryData(['uiTestCase', caseId], nextCase)
  }

  function toggleStepPanel(index: number) {
    setExpandedStepIndexes((current) => (current.includes(index) ? current.filter((item) => item !== index) : [...current, index]))
  }

  function addStep(add: (defaultValue?: UiTestStepFormValue, insertIndex?: number) => void, stepCount: number) {
    add(
      {
        enabled: true,
        continueOnFailure: false,
      },
      stepCount,
    )
    setExpandedStepIndexes((current) => [...current, stepCount])
  }

  function removeStep(remove: (index: number | number[]) => void, index: number) {
    remove(index)
    setExpandedStepIndexes((current) =>
      current
        .filter((item) => item !== index)
        .map((item) => (item > index ? item - 1 : item)),
    )
  }

  function moveStep(move: (from: number, to: number) => void, fromIndex: number, toIndex: number) {
    move(fromIndex, toIndex)
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

  function getTemplatePickerKey(stepIndex: number, fieldKey: UiTemplateFieldKey) {
    return `step-${stepIndex}-${fieldKey}`
  }

  function bindTemplateInputRef(stepIndex: number, fieldKey: UiTemplateFieldKey) {
    return (instance: InputRef | null) => {
      templateInputRefs.current[getTemplateRefKey(stepIndex, fieldKey)] = instance
    }
  }

  function insertBuiltinTemplate(stepIndex: number, fieldKey: UiTemplateFieldKey, token: string) {
    const path: ['steps', number, UiTemplateFieldKey] = ['steps', stepIndex, fieldKey]
    const currentValue = (caseForm.getFieldValue(path) as string | undefined) ?? ''
    const inputRef = templateInputRefs.current[getTemplateRefKey(stepIndex, fieldKey)]
    const inputElement = inputRef?.input ?? null

    if (!inputElement) {
      caseForm.setFieldValue(path, `${currentValue}${token}`)
      setTemplatePickerOpenKey(null)
      return
    }

    const selectionStart = inputElement.selectionStart ?? currentValue.length
    const selectionEnd = inputElement.selectionEnd ?? currentValue.length
    const nextValue = `${currentValue.slice(0, selectionStart)}${token}${currentValue.slice(selectionEnd)}`
    const nextCursor = selectionStart + token.length

    caseForm.setFieldValue(path, nextValue)
    setTemplatePickerOpenKey(null)

    requestAnimationFrame(() => {
      inputElement.focus()
      inputElement.setSelectionRange(nextCursor, nextCursor)
    })
  }

  function renderTemplatePickerContent(stepIndex: number, fieldKey: UiTemplateFieldKey) {
    return (
      <div className="ui-template-picker">
        <div className="ui-template-picker-head">
          <div className="ui-template-picker-title">插入内置函数</div>
          <div className="ui-template-picker-subtitle">
            当前只会渲染
            <strong>{` ${UI_TEMPLATE_FIELD_LABELS[fieldKey]} `}</strong>
            里的内置函数模板，普通变量占位 <code>{'{{token}}'}</code> 不会生效。
          </div>
        </div>
        <div className="ui-template-picker-list">
          {uiBuiltinTemplateFunctions.map((item) => (
            <button
              key={`${fieldKey}-${item.token}`}
              type="button"
              className="ui-template-picker-item"
              onClick={() => insertBuiltinTemplate(stepIndex, fieldKey, item.token)}
            >
              <div className="ui-template-picker-item-head">
                <span className="ui-template-picker-item-label">{item.label}</span>
                <code className="ui-template-picker-item-token">{item.token}</code>
              </div>
              <div className="ui-template-picker-item-desc">{item.description}</div>
              {item.example ? <div className="ui-template-picker-item-example">示例：{item.example}</div> : null}
            </button>
          ))}
        </div>
      </div>
    )
  }

  function renderTemplatePickerLabel(stepIndex: number, fieldKey: UiTemplateFieldKey, label: string) {
    const pickerKey = getTemplatePickerKey(stepIndex, fieldKey)

    return (
      <div className="ui-template-picker-label">
        <span>{label}</span>
        <Popover
          trigger="click"
          placement="bottomLeft"
          open={templatePickerOpenKey === pickerKey}
          onOpenChange={(open) => setTemplatePickerOpenKey(open ? pickerKey : null)}
          overlayClassName="ui-template-picker-overlay"
          content={renderTemplatePickerContent(stepIndex, fieldKey)}
        >
          <Button type="link" size="small" className="ui-template-picker-trigger" icon={<CodeOutlined />}>
            内置函数
          </Button>
        </Popover>
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
        caseForm.setFieldsValue(createDefaultUiTestCaseFormValues())
      }
      queryClient.removeQueries({ queryKey: ['uiTestCase', caseId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['uiTestCases', suiteId] })
    },
  })

  const debugRunMutation = useMutation({
    mutationFn: () => {
      if (!activeCaseId) {
        throw new Error('未选择可运行的 UI测试用例')
      }

      return api.debugRunUiTestCase(activeCaseId, buildUiSuiteDebugRunPayload(suiteQuery.data))
    },
    onSuccess: (runRecord) => {
      const runId = getUiTestCaseRunId(runRecord)
      if (!runId) {
        message.error('未获取到运行记录 ID')
        return
      }

      queryClient.setQueryData(['uiTestCaseRun', runId], runRecord)
      setSelectedRunId(runId)
      setUiRunView('steps')
      message.success(isUiRunPollingStatus(runRecord.status) ? '已开始调试运行' : '调试运行记录已创建')
    },
  })
  const runSuiteMutation = useMutation({
    mutationFn: () => {
      if (!suiteId) {
        throw new Error('未找到可运行的 UI测试集')
      }

      return api.runUiTestSuite(suiteId, buildUiSuiteRunPayload(suiteQuery.data))
    },
    onSuccess: (runRecord) => {
      const suiteRunId = getUiTestSuiteRunId(runRecord)
      if (!suiteRunId) {
        message.error('未获取到运行记录 ID')
        return
      }

      queryClient.setQueryData<UiTestSuiteRunSummary[]>(['uiTestSuiteRuns', suiteId], (current) => {
        const currentItems = current ?? []
        return [runRecord, ...currentItems.filter((item) => item.suiteRunId !== suiteRunId)]
      })

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
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      caseOrderRollbackRef.current = []
      setDraggingCaseId(null)
    },
  })

  const importUiCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) => api.importUiTestCases(suiteId, file, filename),
    onSuccess: (result) => {
      message.success(`导入成功：${result.importedCaseCount ?? 0} 条用例，${result.importedStepCount ?? 0} 个步骤`)
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

  const filteredCases = useMemo(() => {
    const keyword = caseSearch.trim().toLowerCase()
    if (!keyword) return uiTestCases

    return uiTestCases.filter((item) =>
      [item.name, item.stepsJson]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keyword)),
    )
  }, [caseSearch, uiTestCases])

  const orderedByRuleCases = useMemo(() => sortUiTestCases(filteredCases), [filteredCases])

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
    if (caseOrderIds.length === 0) return orderedByRuleCases

    const caseMap = new Map(orderedByRuleCases.map((item) => [normalizeUiTestCaseId(item), item]))
    const ordered = caseOrderIds.map((caseId) => caseMap.get(caseId)).filter(Boolean) as UiTestCase[]
    const missing = orderedByRuleCases.filter((item) => !caseOrderIds.includes(normalizeUiTestCaseId(item)))
    return [...ordered, ...missing]
  }, [caseOrderIds, orderedByRuleCases])

  const sidebarCases = useMemo(() => (draftCase ? [...orderedCases, draftCase] : orderedCases), [draftCase, orderedCases])
  const canReorder = can('write') && caseSearch.trim().length === 0

  const suiteMeta = useMemo(
    () => [
      { label: '测试集', value: suiteQuery.data?.name || '-' },
      { label: '需求', value: requirementQuery.data?.name || requirementId || '-' },
      { label: '迭代', value: sprintQuery.data?.name || sprintId || '-' },
      { label: '运行模式', value: suiteQuery.data?.headless === undefined ? '-' : suiteQuery.data.headless ? '无头模式' : '可视模式' },
      { label: '慢放延迟', value: formatOptionalMs(suiteQuery.data?.slowMoMs) },
      { label: '视口', value: formatViewportText(suiteQuery.data?.viewportWidth, suiteQuery.data?.viewportHeight) },
      { label: '步骤超时', value: formatOptionalMs(suiteQuery.data?.defaultStepTimeoutMs) },
      { label: '截图策略', value: formatUiScreenshotPolicy(suiteQuery.data?.screenshotPolicy) },
    ],
    [requirementId, requirementQuery.data?.name, sprintId, sprintQuery.data?.name, suiteQuery.data],
  )

  useEffect(() => {
    setSelectedCaseId('')
    setCaseSearch('')
    setDraftCaseValues(null)
    setEditingCase(null)
    setExpandedStepIndexes([])
    setDraggingStepIndex(null)
    setSelectedRunId('')
    setUiRunView('steps')
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
    setTemplatePickerOpenKey(null)
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
    setExpandedStepIndexes([])
    setDraggingStepIndex(null)
    setSelectedRunId('')
    setUiRunView('steps')
  }, [selectedCaseId])

  useEffect(() => {
    const currentRun = activeSuiteRunQuery.data
    if (!currentRun?.suiteRunId) return

    queryClient.setQueryData<UiTestSuiteRunSummary[]>(['uiTestSuiteRuns', suiteId], (current) => {
      const currentItems = current ?? []
      return [currentRun, ...currentItems.filter((item) => item.suiteRunId !== currentRun.suiteRunId)]
    })

    if (!isUiRunPollingStatus(currentRun.status)) {
      setActivePollingSuiteRunId((current) => (current === currentRun.suiteRunId ? '' : current))
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

  useEffect(() => {
    if (!activeCaseId || !selectedCaseDetailQuery.data) return

    setEditingCase(selectedCaseDetailQuery.data)
    caseForm.setFieldsValue(buildUiTestCaseFormValues(selectedCaseDetailQuery.data))
  }, [activeCaseId, caseForm, selectedCaseDetailQuery.data])

  useEffect(() => {
    if (!selectedRunId) return

    function syncEditorTopHeight() {
      const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
      if (containerHeight === 0) return

      setEditorTopHeight((current) => getNextEditorTopHeight({
        currentHeight: current,
        deltaY: 0,
        containerHeight,
        minTopHeight: MIN_EDITOR_TOP_HEIGHT,
        minResultHeight: MIN_EDITOR_RESULT_HEIGHT,
        splitterHeight: EDITOR_SPLITTER_HEIGHT,
      }))
    }

    syncEditorTopHeight()
    window.addEventListener('resize', syncEditorTopHeight)

    return () => {
      window.removeEventListener('resize', syncEditorTopHeight)
    }
  }, [selectedRunId])

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

  useEffect(() => {
    if (sidebarCases.length === 0) {
      if (selectedCaseId) {
        setSelectedCaseId('')
        setEditingCase(null)
      }
      return
    }

    const exists = sidebarCases.some((item) => normalizeUiTestCaseId(item) === selectedCaseId)
    if (!selectedCaseId || !exists) {
      setSelectedCaseId(normalizeUiTestCaseId(sidebarCases[0]))
    }
  }, [selectedCaseId, sidebarCases])

  function openCreateCase() {
    const nextDraft = draftCaseValues ?? createDefaultUiTestCaseFormValues()
    setDraftCaseValues(nextDraft)
    setSelectedCaseId(DRAFT_CASE_ID)
    setEditingCase(null)
    caseForm.setFieldsValue(nextDraft)
  }

  function handleDebugRun() {
    if (!activeCaseId || isCreatingCase) return

    if (hasUnsavedCaseChanges) {
      message.warning('当前页面还有未保存修改，调试运行会基于最近一次保存的用例内容。')
    }

    debugRunMutation.mutate()
  }

  function handleEditorPanelResize(deltaY: number) {
    const containerHeight = editorLayoutRef.current?.getBoundingClientRect().height ?? 0
    if (containerHeight === 0) return

    setEditorTopHeight((current) => getNextEditorTopHeight({
      currentHeight: current,
      deltaY,
      containerHeight,
      minTopHeight: MIN_EDITOR_TOP_HEIGHT,
      minResultHeight: MIN_EDITOR_RESULT_HEIGHT,
      splitterHeight: EDITOR_SPLITTER_HEIGHT,
    }))
  }

  function handleRunSuite() {
    if (!suiteId || uiTestCases.length === 0) return

    if (hasUnsavedCaseChanges) {
      message.warning('当前页面还有未保存修改，正式运行会基于最近一次保存的用例内容。')
    }

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
    setActivePollingSuiteRunId((current) => (current === selectedSuiteRunId ? '' : current))
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
    const fallbackCase = orderedCases[0] ?? null
    if (fallbackCase) {
      setSelectedCaseId(normalizeUiTestCaseId(fallbackCase))
      return
    }

    setSelectedCaseId('')
    setEditingCase(null)
    caseForm.setFieldsValue(createDefaultUiTestCaseFormValues())
  }

  function handleCaseDragStart(event: DragEvent<HTMLDivElement>, caseId: string) {
    if (!canReorder || caseId === DRAFT_CASE_ID) return
    setDraggingCaseId(caseId)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', caseId)
  }

  function handleCaseDrop(targetCaseId: string) {
    if (!draggingCaseId || draggingCaseId === targetCaseId || !canReorder) return
    if (draggingCaseId === DRAFT_CASE_ID || targetCaseId === DRAFT_CASE_ID) return

    const baseOrderIds = (caseOrderIds.length > 0 ? caseOrderIds : orderedCases.map((item) => normalizeUiTestCaseId(item)).filter(Boolean)).filter(
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
  const hasUnsavedCaseChanges = !isCreatingCase && caseForm.isFieldsTouched()
  const currentRun = uiTestCaseRunQuery.data ?? null
  const currentRunStatusMeta = getExecutionStatusMeta(currentRun?.status)
  const currentRunStepResults = useMemo(
    () =>
      [...(currentRun?.stepResults ?? [])].sort(
        (left, right) => (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER),
      ),
    [currentRun?.stepResults],
  )
  const suiteRunHistory = useMemo(
    () =>
      [...listItems(suiteRunHistoryQuery.data)].sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [suiteRunHistoryQuery.data],
  )
  const suiteRunReport = suiteRunReportQuery.data ?? null
  const selectedSuiteRunSummary = useMemo(
    () =>
      (selectedSuiteRunId && activeSuiteRunQuery.data?.suiteRunId === selectedSuiteRunId ? activeSuiteRunQuery.data : undefined) ??
      suiteRunHistory.find((item) => item.suiteRunId === selectedSuiteRunId) ??
      null,
    [activeSuiteRunQuery.data, selectedSuiteRunId, suiteRunHistory],
  )
  const orderedSuiteRunItems = useMemo(
    () =>
      [...(suiteRunReport?.items ?? [])].sort(
        (left, right) =>
          (left.orderNo ?? Number.MAX_SAFE_INTEGER) - (right.orderNo ?? Number.MAX_SAFE_INTEGER) ||
          (left.caseName ?? '').localeCompare(right.caseName ?? ''),
      ),
    [suiteRunReport?.items],
  )

  function renderUiRunContent() {
    if (!currentRun) {
      return <Empty description="运行详情加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
    }

    if (uiRunView === 'snapshot') {
      const snapshotSections = [
        { label: '浏览器信息', value: currentRun.snapshot?.browser },
        { label: '运行配置', value: currentRun.snapshot?.options },
      ].filter((item) => item.value !== undefined && item.value !== null)

      if (snapshotSections.length === 0) {
        return <Empty description="暂无运行快照" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      }

      return (
        <div className="api-case-run-result-list">
          {snapshotSections.map((section) => (
            <div key={section.label} className="api-case-run-result-row">
              <div className="api-case-run-result-row-title">
                <strong>{section.label}</strong>
              </div>
              <pre className="api-case-run-result-pre compact">{prettyPrintValue(section.value)}</pre>
            </div>
          ))}
        </div>
      )
    }

    if (currentRunStepResults.length === 0) {
      return (
        <Empty
          description={isUiRunPollingStatus(currentRun.status) ? '步骤结果生成中...' : '暂无步骤结果'}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      )
    }

    return renderUiRunStepResultList(currentRunStepResults, isUiRunPollingStatus(currentRun.status) ? '步骤结果生成中...' : '暂无步骤结果')
  }

  return (<ProjectAccessScope projectId={sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? ''}>{(
    <div className="workbench-page api-automation-page">
      <div className="api-automation-content">
        <div className="page-frame api-collection-detail-frame">
          <div className="api-collection-detail-layout ui-suite-case-layout">
            {suiteQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suiteQuery.error)} /> : null}
            {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}
            {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getErrorMessage(selectedCaseDetailQuery.error)} /> : null}
            {requirementQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementQuery.error)} /> : null}
            {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}

            <aside className="workbench-panel api-case-sidebar ui-suite-case-sidebar">
              <div className="panel-header api-case-sidebar-header">
                <div className="api-case-sidebar-title">
                  <Button
                    type="text"
                    icon={<ArrowLeftOutlined />}
                    className="api-case-back-button"
                    onClick={() => navigate('/ui-automation')}
                    aria-label="返回 UI测试集列表"
                  />
                  <div className="api-case-sidebar-title-copy">
                    <Title level={5}>UI测试用例</Title>
                    <Text type="secondary" className="api-case-sidebar-count">
                      {sidebarCases.length} 个用例
                    </Text>
                  </div>
                </div>
                <div className="api-case-sidebar-meta">
                  <Tooltip title="新建用例">
                    <ProjectActionButton action="write"
                      type="text"
                      className="action-btn-create"
                      operation="create" iconOnly
                      aria-label="新建 UI测试用例"
                      onClick={openCreateCase}
                      disabled={!suiteId}
                    />
                  </Tooltip>
                </div>
              </div>

              <div className="api-case-sidebar-toolbar">
                <Input.Search
                  placeholder="搜索用例名称 / 步骤"
                  allowClear
                  value={caseSearch}
                  onChange={(event) => setCaseSearch(event.target.value)}
                />
                <ProjectActionButton action="execute" className="api-case-import-trigger" operation="upload" onClick={openCaseImportModal} disabled={!suiteId}>
                  用例导入
                </ProjectActionButton>
              </div>

              <div className="api-case-sidebar-scroll">
                {casesQuery.isLoading ? (
                  <div className="sprint-card-loading">
                    <Empty description="UI测试用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                ) : sidebarCases.length === 0 ? (
                  <div className="ui-suite-case-empty-list">
                    <Empty description="当前测试集还没有 UI测试用例">
                      <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                        新建用例
                      </ProjectActionButton>
                    </Empty>
                  </div>
                ) : (
                  <div className="api-case-nav-list">
                    {sidebarCases.map((item) => {
                      const caseId = normalizeUiTestCaseId(item)
                      const selected = caseId === selectedCaseId
                      const stepCount = getUiTestCaseStepCount(item)

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
                          onClick={() => setSelectedCaseId(caseId)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              setSelectedCaseId(caseId)
                            }
                          }}
                        >
                          <div className="api-case-nav-item-main">
                            <div className="api-case-nav-item-tags">
                              <Tag color={item.enabled === false ? 'default' : 'success'}>
                                {item.enabled === false ? '停用' : '启用'}
                              </Tag>
                              {caseId === DRAFT_CASE_ID ? <Tag color="gold">草稿</Tag> : null}
                            </div>
                            <span className="api-case-nav-item-name">{item.name}</span>
                            <span className="api-case-nav-item-path">{stepCount} 步</span>
                          </div>
                          <div
                            className="api-case-nav-item-actions"
                            onClick={(event) => event.stopPropagation()}
                            onMouseDown={(event) => event.stopPropagation()}
                          >
                            <Popconfirm
                              title={caseId === DRAFT_CASE_ID ? '确认丢弃这个未保存用例？' : '确认删除该 UI测试用例？'}
                              onConfirm={() => {
                                if (caseId === DRAFT_CASE_ID) {
                                  handleDiscardDraft()
                                  return
                                }
                                deleteCaseMutation.mutate(caseId)
                              }}
                            >
                              <Tooltip title="删除">
                                <ProjectActionButton action="write"
                                  danger
                                  type="text"
                                  size="small"
                                  className="api-case-nav-delete action-btn-delete"
                                  operation="delete" iconOnly
                                  loading={deleteCaseMutation.isPending && !isCreatingCase && selectedCaseId === caseId}
                                  aria-label="删除 UI测试用例"
                                />
                              </Tooltip>
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
              {suiteQuery.data ? (
                <div className="api-detail-hover-panel api-collection-detail-panel ui-suite-case-detail-panel">
                  <div className="api-detail-hover-bar">
                    <div className="api-detail-hover-bar-main">
                      <span className="api-detail-hover-title">UI测试集详情</span>
                      <span className="api-detail-hover-preview">
                        {suiteQuery.data.name} / {requirementQuery.data?.name ?? requirementId ?? '-'} / {sprintQuery.data?.name ?? sprintId ?? '-'}
                      </span>
                    </div>
                    <div className="api-detail-hover-bar-actions">
                      <Button className="action-btn-read" onClick={() => setSuiteRunHistoryOpen(true)}>
                        运行记录
                      </Button>
                      <ProjectActionButton action="execute"
                        type="primary"
                        operation="run"
                        loading={runSuiteMutation.isPending}
                        onClick={handleRunSuite}
                        disabled={uiTestCases.length === 0}
                      >
                        运行测试集
                      </ProjectActionButton>
                    </div>
                  </div>
                  <div className="api-detail-hover-body">
                    <p className="api-detail-description">
                      {suiteQuery.data.description || '在这里管理当前 UI测试集下的测试用例，步骤会直接保存在用例的 stepsJson 中。'}
                    </p>
                    <Card className="detail-block api-case-summary-card">
                      <div className="api-case-summary-grid compact ui-suite-case-summary-grid">
                        {suiteMeta.map((item) => (
                          <div key={item.label} className="api-summary-item ui-suite-case-summary-item">
                            <Text type="secondary">{item.label}</Text>
                            <strong>{item.value}</strong>
                          </div>
                        ))}
                      </div>
                    </Card>
                  </div>
                </div>
              ) : null}

              <section className="workbench-panel api-case-editor-panel ui-suite-case-editor-panel">
                <div className="api-case-editor-shell" ref={editorLayoutRef}>
                  <div className="api-case-editor-main" style={selectedRunId ? { flex: `0 0 ${editorTopHeight}px` } : undefined}>
                    <div className="api-case-editor-main-scroll">
                      {!selectedCaseId ? (
                        <div className="ui-test-case-empty-editor">
                          <Empty description="请选择一个 UI测试用例，或先新建一个用例">
                            <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                              新建用例
                            </ProjectActionButton>
                          </Empty>
                        </div>
                      ) : !showEditorForm && selectedCaseDetailQuery.isLoading ? (
                        <div className="ui-test-case-empty-editor">
                          <Empty description="UI测试用例详情加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                        </div>
                      ) : showEditorForm ? (
                        <Form<UiTestCaseFormValues>
                          form={caseForm}
                          layout="vertical"
                          requiredMark={false}
                          className="ui-test-case-form"
                          onValuesChange={(_changedValues, allValues) => {
                            if (isCreatingCase) {
                              setDraftCaseValues(allValues as UiTestCaseFormValues)
                            }
                          }}
                          onFinish={(values) => {
                            const completeValues = {
                              ...getCompleteCaseFormValues(),
                              ...values,
                              steps: values.steps ?? getCompleteCaseFormValues().steps,
                            } satisfies UiTestCaseFormValues

                            if (isCreatingCase) {
                              createCaseMutation.mutate(completeValues)
                              return
                            }

                            if (!editingCase || normalizeUiTestCaseId(editingCase) !== activeCaseId) {
                              message.warning('用例详情加载中，请稍后再试')
                              return
                            }

                            const payload = buildUiTestCaseUpdatePayload(editingCase, {
                              name: completeValues.name,
                              enabled: completeValues.enabled,
                              orderNo: editingCase.orderNo,
                              stepsJson: serializeSteps(completeValues.steps),
                            })

                            if (Object.keys(payload).length === 0) {
                              message.info('当前没有需要保存的修改')
                              return
                            }

                            updateCaseMutation.mutate(completeValues)
                          }}
                        >
                          <div className="ui-test-case-editor-fixed-head">
                            <div className="ui-test-case-toolbar">
                              <div className="ui-test-case-name-block">
                                <div className="ui-test-case-inline-label">用例名称</div>
                                <Form.Item name="name" className="ui-test-case-name-item" rules={[{ required: true, message: '请输入 UI测试用例名称' }]}>
                                  <Input maxLength={120} placeholder="例如：登录成功验证" />
                                </Form.Item>
                              </div>
                              <div className="ui-test-case-toolbar-meta">
                                <ProjectActionButton action="execute"
                                  className="action-btn-read"
                                  operation="run"
                                  onClick={handleDebugRun}
                                  loading={debugRunMutation.isPending}
                                  disabled={!activeCaseId || isCreatingCase}
                                >
                                  调试运行
                                </ProjectActionButton>
                                <ProjectActionButton action="write"
                                  type="primary"
                                  className="action-btn-save"
                                  operation="save"
                                  loading={createCaseMutation.isPending || updateCaseMutation.isPending}
                                  onClick={() => caseForm.submit()}
                                >
                                  保存
                                </ProjectActionButton>
                              </div>
                            </div>
                            <div className="ui-test-case-secondary-meta" aria-live="polite">
                              <div className="ui-test-case-enabled-meta">
                                <Form.Item name="enabled" valuePropName="checked">
                                  <Switch size="small" aria-label="启用当前用例" />
                                </Form.Item>
                                <span>{watchedEnabled ? '当前用例已启用' : '当前用例已停用'}</span>
                              </div>
                              <span className="ui-test-case-meta-separator" aria-hidden="true">·</span>
                              <span className="ui-test-case-step-count-meta">
                                <UnorderedListOutlined aria-hidden="true" />
                                包含 {watchedSteps.length} 个步骤
                              </span>
                            </div>
                          </div>

                          <div className="ui-test-case-step-section">
                            <div className="ui-test-case-step-scroll">
                              <div className="ui-test-case-step-toolbar">
                                <div>
                                  <div className="ui-test-case-step-title">步骤编辑器</div>
                                </div>
                              </div>

                              <UiStepEditor addStep={addStep} watchedSteps={watchedSteps} expandedStepIndexes={expandedStepIndexes} draggingStepIndex={draggingStepIndex} handleStepDrop={handleStepDrop} can={can} handleStepDragStart={handleStepDragStart} setDraggingStepIndex={setDraggingStepIndex} toggleStepPanel={toggleStepPanel} removeStep={removeStep} renderTemplatePickerLabel={renderTemplatePickerLabel} bindTemplateInputRef={bindTemplateInputRef} />
                            </div>
                          </div>
                        </Form>
                      ) : (
                        <div className="ui-test-case-empty-editor">
                          <Empty description="未找到对应的 UI测试用例" />
                        </div>
                      )}
                    </div>
                  </div>
                  {selectedRunId ? (
                    <>
                      <UiTestPanelSplitter onResize={handleEditorPanelResize} />
                      <div className="api-case-editor-result-pane">
                        <div className="api-case-editor-result-scroll">
                          <Card size="small" className="api-case-run-result-card">
                            <div className="api-case-run-result-head">
                              <div className="api-case-run-result-title">
                                <Text strong>调试结果</Text>
                                {currentRun ? <Tag color={currentRunStatusMeta.color}>{currentRunStatusMeta.label}</Tag> : null}
                                {currentRun && typeof currentRun.success === 'boolean' ? (
                                  <Tag color={currentRun.success ? 'success' : 'error'}>{currentRun.success ? '成功' : '失败'}</Tag>
                                ) : null}
                              </div>
                              <div className="api-case-run-result-meta">
                                <span>运行 ID：{selectedRunId || '-'}</span>
                                <span>耗时：{currentRun?.durationMs ?? 0} ms</span>
                                <span>当前 URL：{currentRun?.currentUrl || '-'}</span>
                                <span>Trace：{currentRun?.tracePath || '-'}</span>
                              </div>
                            </div>
                            {uiTestCaseRunQuery.error && !currentRun ? (
                              <Alert showIcon type="error" title={getErrorMessage(uiTestCaseRunQuery.error)} className="api-case-run-result-alert" />
                            ) : null}
                            {currentRun?.errorMessage ? (
                              <Alert showIcon type="error" title={currentRun.errorMessage} className="api-case-run-result-alert" />
                            ) : null}
                            <Segmented
                              className="api-case-run-result-segmented"
                              options={uiTestRunViewOptions}
                              value={uiRunView}
                              onChange={(value) => setUiRunView(value as UiTestRunView)}
                            />
                            <div className="api-case-run-result-block">{renderUiRunContent()}</div>
                            <div className="ui-test-run-inline-actions">
                              <ActionButton operation="refresh" onClick={handleRefreshUiRunDetail} loading={uiTestCaseRunQuery.isFetching}>
                                刷新
                              </ActionButton>
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

        <UiCaseImportModal caseImportModalOpen={caseImportModalOpen} closeCaseImportModal={closeCaseImportModal} importUiCasesMutation={importUiCasesMutation} handleImportUiCases={handleImportUiCases} caseImportMode={caseImportMode} setCaseImportMode={setCaseImportMode} setImportYamlFile={setImportYamlFile} importYamlText={importYamlText} setImportYamlText={setImportYamlText} />

        <UiSuiteRunHistory suiteRunHistoryOpen={suiteRunHistoryOpen} setSuiteRunHistoryOpen={setSuiteRunHistoryOpen} suiteRunHistoryQuery={suiteRunHistoryQuery} suiteRunHistory={suiteRunHistory} loadingSuiteRunHistoryId={loadingSuiteRunHistoryId} handleOpenSuiteRunHistoryItem={handleOpenSuiteRunHistoryItem} />

        <UiSuiteRunReport suiteRunReportOpen={suiteRunReportOpen} closeSuiteRunReport={closeSuiteRunReport} suiteRunReportQuery={suiteRunReportQuery} suiteRunReport={suiteRunReport} handleRefreshSuiteRunReport={handleRefreshSuiteRunReport} refreshingSuiteRunReport={refreshingSuiteRunReport} selectedSuiteRunId={selectedSuiteRunId} suiteRunReportView={suiteRunReportView} setSuiteRunReportView={setSuiteRunReportView} orderedSuiteRunItems={orderedSuiteRunItems} selectedSuiteRunSummary={selectedSuiteRunSummary} expandedSuiteRunItemIds={expandedSuiteRunItemIds} toggleSuiteRunItem={toggleSuiteRunItem} />
      </div>
    </div>
  )}</ProjectAccessScope>)
}
