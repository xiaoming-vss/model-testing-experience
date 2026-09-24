import { Text } from '@/features/ui-automation/utils/detailView'
import { UiCaseImportModal } from '@/features/ui-automation/components/UiCaseImportModal'
import { UiCaseControlRibbon } from '@/features/ui-automation/components/UiCaseControlRibbon'
import { UiCaseMetaBar } from '@/features/ui-automation/components/UiCaseMetaBar'
import { UiCaseOrderPopover } from '@/features/ui-automation/components/UiCaseOrderPopover'
import { UiRunInspector } from '@/features/ui-automation/components/UiRunInspector'
import { UiStepEditor } from '@/features/ui-automation/components/UiStepEditor'
import { UiSuiteDetailToolbar } from '@/features/ui-automation/components/UiSuiteDetailToolbar'
import { UiSuiteRunHistory } from '@/features/ui-automation/components/UiSuiteRunHistory'
import { UiSuiteRunReport } from '@/features/ui-automation/components/UiSuiteRunReport'
import { UI_TEMPLATE_FIELD_LABELS, isYamlFileName, type CaseImportMode, type UiTemplateFieldKey } from '@/features/ui-automation/utils/detailView'

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
import { uiBuiltinTemplateFunctions } from '@/shared/constants/templateFunctions'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage,
  normalizeUiTestCaseId
} from '@/utils/format'
import { buildUiTestCaseUpdatePayload } from '@/utils/updatePayload'
import { CodeOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InputRef } from 'antd'
import { Alert, Button, Empty, Form, Popover } from 'antd'
import { useEffect, useMemo, useRef, useState, type DragEvent } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { UiSuiteRunReportView } from '../config/stepConfig'
import { formatUiScreenshotPolicy } from '../constants/defaultRunConfig'
import { formatUiCaseSerial, formatUiRunRelativeTime, getUiSuiteReadiness } from '../utils/detailRunView'
import {
  buildUiSuiteDebugRunPayload,
  buildUiSuiteRunPayload,
  getUiTestCaseRunId,
  getUiTestSuiteRunId,
  isUiRunPollingStatus
} from '../utils/runHelpers'
import {
  DRAFT_CASE_ID,
  EMPTY_UI_TEST_CASES,
  buildUiTestCaseFormValues,
  createDefaultUiTestCaseFormValues,
  formatViewportText,
  moveArrayItem,
  moveExpandedStepIndex,
  serializeSteps,
  serializeUiTestCaseValues,
  sortUiTestCases,
  type UiTestCaseFormValues,
  type UiTestStepFormValue
} from '../utils/uiTestCaseEditor'
import '@/shared/styles/surface-tokens.css'
import '@/features/ui-automation/styles/detail-workbench-v2.css'
import '@/features/ui-automation/styles/detail-pipeline-v2.css'
import '@/features/ui-automation/styles/detail-inspector-v2.css'

export function UiTestSuiteCasePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const { suiteId = '' } = useParams<{ suiteId: string }>()
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [draftCaseValues, setDraftCaseValues] = useState<UiTestCaseFormValues | null>(null)
  const [editingCase, setEditingCase] = useState<UiTestCase | null>(null)
  const [caseOrderIds, setCaseOrderIds] = useState<string[]>([])
  const [draggingCaseId, setDraggingCaseId] = useState<string | null>(null)
  const [expandedStepIndexes, setExpandedStepIndexes] = useState<number[]>([])
  const [draggingStepIndex, setDraggingStepIndex] = useState<number | null>(null)
  const [selectedRunId, setSelectedRunId] = useState('')
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
  // 顶栏的「上次运行」与运行记录条数都要用这份历史，所以它不再等抽屉打开才启用。
  const suiteRunHistoryQuery = useQuery({
    queryKey: ['uiTestSuiteRuns', suiteId],
    queryFn: () => api.getUiTestSuiteRuns(suiteId),
    enabled: Boolean(suiteId),
    refetchOnWindowFocus: false,
    refetchInterval: (query) => {
      const data = query.state.data as UiTestSuiteRunSummary[] | undefined
      return (data ?? []).some((item) => isUiRunPollingStatus(item.status)) ? 3000 : false
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

  /** 批量启用/禁用：一次写回所有步骤的 enabled，未保存的改动仍由「保存」统一提交。 */
  function handleToggleAllSteps() {
    const steps = caseForm.getFieldValue('steps') as UiTestStepFormValue[] | undefined
    if (!steps?.length) return

    const nextEnabled = !steps.every((step) => step?.enabled !== false)
    caseForm.setFieldsValue({ steps: steps.map((step) => ({ ...step, enabled: nextEnabled })) })
    if (isCreatingCase) {
      setDraftCaseValues((current) => (current ? { ...current, steps: steps.map((step) => ({ ...step, enabled: nextEnabled })) } : current))
    }
    message.success(nextEnabled ? '已启用全部步骤，保存后生效' : '已禁用全部步骤，保存后生效')
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
      [...listItems(suiteRunHistoryQuery.data)].sort((left, right) => {
        const leftTime = new Date(left.startedAt || left.createdAt || left.updatedAt || '').getTime()
        const rightTime = new Date(right.startedAt || right.createdAt || right.updatedAt || '').getTime()
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime)
      }),
    [suiteRunHistoryQuery.data],
  )
  const latestSuiteRun = useMemo(
    () =>
      (activeSuiteRunQuery.data?.suiteRunId === selectedSuiteRunId ? activeSuiteRunQuery.data : undefined) ??
      suiteRunHistory[0] ??
      null,
    [activeSuiteRunQuery.data, selectedSuiteRunId, suiteRunHistory],
  )
  const readiness = useMemo(() => getUiSuiteReadiness(latestSuiteRun), [latestSuiteRun])

  const suiteRunReport = suiteRunReportQuery.data ?? null
  const selectedSuiteRunSummary = useMemo(
    () => suiteRunHistory.find((item) => item.suiteRunId === selectedSuiteRunId) ?? null,
    [selectedSuiteRunId, suiteRunHistory],
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

  const currentRun = uiTestCaseRunQuery.data ?? null
  // 步骤卡片上的 PASS / FAIL 徽标取自最近一次调试运行，按顺序号对齐当前用例的步骤。
  const currentRunStepResults = useMemo(
    () => [...(currentRun?.stepResults ?? [])],
    [currentRun?.stepResults],
  )
  const caseSerial = formatUiCaseSerial(editingCase?.orderNo ?? (isCreatingCase ? undefined : orderedCases.findIndex((item) => normalizeUiTestCaseId(item) === activeCaseId) + 1))
  const runEnvText = useMemo(() => {
    const suite = suiteQuery.data
    const viewport = formatViewportText(suite?.viewportWidth, suite?.viewportHeight)
    return [
      suite?.headless === undefined ? '' : suite.headless ? '无头模式' : '可视模式',
      viewport === '-' ? '' : viewport,
      suite?.slowMoMs ? `慢放 ${suite.slowMoMs}ms` : '',
      suite?.defaultStepTimeoutMs ? `步骤超时 ${suite.defaultStepTimeoutMs}ms` : '',
    ]
      .filter(Boolean)
      .join(' · ') || '默认运行配置'
  }, [suiteQuery.data])
  const screenshotText = formatUiScreenshotPolicy(suiteQuery.data?.screenshotPolicy)

  useEffect(() => {
    setSelectedCaseId('')
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
  }, [selectedCaseId])

  useEffect(() => {
    const currentSuiteRun = activeSuiteRunQuery.data
    if (!currentSuiteRun?.suiteRunId) return

    queryClient.setQueryData<UiTestSuiteRunSummary[]>(['uiTestSuiteRuns', suiteId], (current) => {
      const currentItems = current ?? []
      return [currentSuiteRun, ...currentItems.filter((item) => item.suiteRunId !== currentSuiteRun.suiteRunId)]
    })

    if (!isUiRunPollingStatus(currentSuiteRun.status)) {
      setActivePollingSuiteRunId((current) => (current === currentSuiteRun.suiteRunId ? '' : current))
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

  function handleSelectCase(caseId: string) {
    setSelectedCaseId(caseId)
  }

  function handleStepCase(delta: number) {
    const currentIndex = caseList.findIndex((item) => normalizeUiTestCaseId(item) === selectedCaseId)
    const nextCase = caseList[currentIndex + delta]
    if (!nextCase) return

    handleSelectCase(normalizeUiTestCaseId(nextCase))
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
  const allStepsEnabled = watchedSteps.length > 0 && watchedSteps.every((step) => step?.enabled !== false)
  const lastRunText = formatUiRunRelativeTime(latestSuiteRun?.startedAt || latestSuiteRun?.createdAt || latestSuiteRun?.updatedAt)

  return (<ProjectAccessScope projectId={sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? ''}>{(
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface ui-test-page ui-suite-detail-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board ui-suite-detail-board">
          {suiteQuery.error ? <Alert showIcon type="error" title={getErrorMessage(suiteQuery.error)} /> : null}
          {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}
          {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getErrorMessage(selectedCaseDetailQuery.error)} /> : null}
          {requirementQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementQuery.error)} /> : null}
          {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
          {uiTestCaseRunQuery.error && !currentRun ? <Alert showIcon type="error" title={getErrorMessage(uiTestCaseRunQuery.error)} /> : null}
          {currentRun?.errorMessage ? <Alert showIcon type="error" title={currentRun.errorMessage} /> : null}

          <UiSuiteDetailToolbar
            suiteName={suiteQuery.data?.name || '-'}
            requirementName={requirementQuery.data?.name ?? requirementId ?? '-'}
            sprintName={sprintQuery.data?.name ?? sprintId ?? '-'}
            readiness={readiness}
            lastRunText={lastRunText}
            runHistoryCount={suiteRunHistory.length}
            runningSuite={runSuiteMutation.isPending}
            debugging={debugRunMutation.isPending}
            saving={createCaseMutation.isPending || updateCaseMutation.isPending}
            canRun={Boolean(suiteId) && uiTestCases.length > 0}
            canDebug={Boolean(activeCaseId) && !isCreatingCase}
            canSave={showEditorForm}
            onBack={() => navigate('/ui-automation')}
            onOpenRunHistory={() => setSuiteRunHistoryOpen(true)}
            onDebugRun={handleDebugRun}
            onRunSuite={handleRunSuite}
            onSave={() => caseForm.submit()}
          />

          <UiCaseControlRibbon
            cases={caseList}
            selectedCaseId={selectedCaseId}
            caseCount={caseList.length}
            runEnvText={runEnvText}
            screenshotText={screenshotText}
            createDisabled={!suiteId}
            onCreateCase={openCreateCase}
            onSelectCase={handleSelectCase}
            onPrevCase={() => handleStepCase(-1)}
            onNextCase={() => handleStepCase(1)}
            orderPopoverContent={
              <UiCaseOrderPopover
                cases={caseList}
                selectedCaseId={selectedCaseId}
                canReorder={canReorder}
                draggingCaseId={draggingCaseId}
                deletingCaseId={deleteCaseMutation.isPending ? activeCaseId : ''}
                onSelect={handleSelectCase}
                onDragStart={handleCaseDragStart}
                onDragEnd={() => setDraggingCaseId(null)}
                onDrop={handleCaseDrop}
                onDelete={(caseId) => deleteCaseMutation.mutate(caseId)}
                onDiscardDraft={handleDiscardDraft}
              />
            }
          />

          <div className="ui-wb-cols">
            <div className="ui-wb-main ui-suite-case-editor-panel">
              {caseList.length === 0 ? (
                <div className="ui-wb-pipeline">
                  <div className="ui-test-case-empty-editor">
                    <Empty description="当前测试集还没有 UI测试用例">
                      <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                        新建用例
                      </ProjectActionButton>
                    </Empty>
                  </div>
                </div>
              ) : !showEditorForm && selectedCaseDetailQuery.isLoading ? (
                <div className="ui-wb-pipeline">
                  <div className="ui-test-case-empty-editor">
                    <Empty description="UI测试用例详情加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
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
                  <UiCaseMetaBar
                    serial={caseSerial}
                    isCreatingCase={isCreatingCase}
                    stepCount={watchedSteps.length}
                    watchedEnabled={watchedEnabled}
                    debugging={debugRunMutation.isPending}
                    saving={createCaseMutation.isPending || updateCaseMutation.isPending}
                    deleting={deleteCaseMutation.isPending}
                    importDisabled={!suiteId}
                    deleteDisabled={!selectedCaseId}
                    onDebugRun={handleDebugRun}
                    onSave={() => caseForm.submit()}
                    onImport={openCaseImportModal}
                    onDelete={() => (isCreatingCase ? handleDiscardDraft() : deleteCaseMutation.mutate(activeCaseId))}
                  />

                  <div className="ui-wb-pipeline">
                    <div className="ui-wb-pipeline-head">
                      <div className="ui-wb-pipeline-title">
                        步骤编辑器
                        <span className="ui-wb-pipeline-chip">Step Pipeline</span>
                      </div>
                      <div className="ui-wb-pipeline-actions">
                        <ProjectActionButton
                          action="write"
                          type="text"
                          size="small"
                          className="ui-wb-pipeline-action"
                          operation="create"
                          icon={<UnorderedListOutlined />}
                          disabled={watchedSteps.length === 0}
                          onClick={handleToggleAllSteps}
                        >
                          {allStepsEnabled ? '全部禁用' : '全部启用'}
                        </ProjectActionButton>
                      </div>
                    </div>
                    <UiStepEditor
                      addStep={addStep}
                      watchedSteps={watchedSteps}
                      expandedStepIndexes={expandedStepIndexes}
                      draggingStepIndex={draggingStepIndex}
                      handleStepDrop={handleStepDrop}
                      can={can}
                      handleStepDragStart={handleStepDragStart}
                      setDraggingStepIndex={setDraggingStepIndex}
                      toggleStepPanel={toggleStepPanel}
                      removeStep={removeStep}
                      renderTemplatePickerLabel={renderTemplatePickerLabel}
                      bindTemplateInputRef={bindTemplateInputRef}
                      stepResults={currentRunStepResults}
                    />
                  </div>
                </Form>
              ) : (
                <div className="ui-wb-pipeline">
                  <div className="ui-test-case-empty-editor">
                    <Empty description="未找到对应的 UI测试用例" />
                  </div>
                </div>
              )}
            </div>

            <UiRunInspector
              run={currentRun}
              viewportText={formatViewportText(suiteQuery.data?.viewportWidth, suiteQuery.data?.viewportHeight)}
              screenshotText={screenshotText}
              refreshing={uiTestCaseRunQuery.isFetching}
              onRefreshRun={handleRefreshUiRunDetail}
            />
          </div>

          {suiteQuery.data?.description ? <Text className="ui-wb-board-note">{suiteQuery.data.description}</Text> : null}
        </section>
      </div>

      <UiCaseImportModal caseImportModalOpen={caseImportModalOpen} closeCaseImportModal={closeCaseImportModal} importUiCasesMutation={importUiCasesMutation} handleImportUiCases={handleImportUiCases} caseImportMode={caseImportMode} setCaseImportMode={setCaseImportMode} setImportYamlFile={setImportYamlFile} importYamlText={importYamlText} setImportYamlText={setImportYamlText} />

      <UiSuiteRunHistory suiteRunHistoryOpen={suiteRunHistoryOpen} setSuiteRunHistoryOpen={setSuiteRunHistoryOpen} suiteRunHistoryQuery={suiteRunHistoryQuery} suiteRunHistory={suiteRunHistory} loadingSuiteRunHistoryId={loadingSuiteRunHistoryId} handleOpenSuiteRunHistoryItem={handleOpenSuiteRunHistoryItem} />

      <UiSuiteRunReport suiteRunReportOpen={suiteRunReportOpen} closeSuiteRunReport={closeSuiteRunReport} suiteRunReportQuery={suiteRunReportQuery} suiteRunReport={suiteRunReport} handleRefreshSuiteRunReport={handleRefreshSuiteRunReport} refreshingSuiteRunReport={refreshingSuiteRunReport} selectedSuiteRunId={selectedSuiteRunId} suiteRunReportView={suiteRunReportView} setSuiteRunReportView={setSuiteRunReportView} orderedSuiteRunItems={orderedSuiteRunItems} selectedSuiteRunSummary={selectedSuiteRunSummary} expandedSuiteRunItemIds={expandedSuiteRunItemIds} toggleSuiteRunItem={toggleSuiteRunItem} />
    </div>
  )}</ProjectAccessScope>)
}
