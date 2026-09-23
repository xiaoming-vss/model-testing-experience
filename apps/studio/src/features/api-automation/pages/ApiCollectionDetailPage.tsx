import { ApiAssertRuleEditor } from '@/features/api-automation/components/ApiAssertRuleEditor'
import { ApiCaseEditor } from '@/features/api-automation/components/ApiCaseEditor'
import { ApiCaseExplorer } from '@/features/api-automation/components/ApiCaseExplorer'
import { ApiCaseImportModal } from '@/features/api-automation/components/ApiCaseImportModal'
import { ApiCaseRunConsole } from '@/features/api-automation/components/ApiCaseRunConsole'
import { ApiCollectionRunHistory } from '@/features/api-automation/components/ApiCollectionRunHistory'
import { ApiCollectionRunReportModal } from '@/features/api-automation/components/ApiCollectionRunReport'
import { ApiCollectionToolbar } from '@/features/api-automation/components/ApiCollectionToolbar'
import { ApiExtractRuleEditor } from '@/features/api-automation/components/ApiExtractRuleEditor'
import { isApiRunPollingStatus, isYamlFileName, type CaseImportMode } from '@/features/api-automation/utils/detailView'
import { useApiCaseEditing } from '../hooks/useApiCaseEditing'
import { useApiCollectionData } from '../hooks/useApiCollectionData'
import { useApiExecution } from '../hooks/useApiExecution'
import { useApiRuleEditing } from '../hooks/useApiRuleEditing'

import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import {
  api,
  listItems,
  type ApiCase,
  type ApiCollectionRunSummary
} from '@/services/api'
import { type JsonEditorRef } from '@/shared/components/JsonEditor/JsonEditor'
import { message } from '@/shared/utils/feedback'
import {
  formatTime,
  getErrorMessage,
  normalizeEnvironmentId,
  pickUpdatedAt
} from '@/utils/format'
import { CheckOutlined, CodeSandboxOutlined, FunctionOutlined, SearchOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { InputRef } from 'antd'
import { Alert, Button, Form, Input, Modal } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import '@/shared/styles/surface-tokens.css'
import '@/features/api-automation/styles/detail-workbench-v2.css'
import '@/features/api-automation/styles/detail-inspector-v2.css'
import '@/features/api-automation/styles/detail-request-panels-v2.css'
import {
  DRAFT_CASE_ID,
  ENV_VAR_TOKEN_PREFIX,
  ENV_VAR_TOKEN_SUFFIX,
  MIN_EDITOR_RESULT_HEIGHT,
  MIN_EDITOR_TOP_HEIGHT,
  builtinTemplateFunctions,
  type EnvVarPickerMode,
  type RunResultView
} from '../config/collectionConfig'
import {
  EMPTY_API_CASES,
  buildApiCaseUpdatePayload,
  buildCaseFormValues,
  createDefaultCaseFormValues,
  getCaseId,
  moveArrayItem,
  sortCasesByOrderNo,
  type ApiCaseFormValues
} from '../utils/apiCaseEditor'
import { buildCollectionRunReportHtml, sanitizeFileName } from '../utils/collectionRunReport'

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

  const [caseImportModalOpen, setCaseImportModalOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importYamlFile, setImportYamlFile] = useState<File | null>(null)
  const [importYamlText, setImportYamlText] = useState('')
  const [editorTopHeight, setEditorTopHeight] = useState(520)
  const [isResizingEditor, setIsResizingEditor] = useState(false)
  const [caseForm] = Form.useForm<ApiCaseFormValues>()

  const caseOrderRollbackRef = useRef<string[]>([])
  const pathInputRef = useRef<InputRef | null>(null)
  const envVarInputRefs = useRef<Record<string, InputRef | null>>({})
  const bodyJsonEditorRef = useRef<JsonEditorRef | null>(null)
  const editorLayoutRef = useRef<HTMLDivElement | null>(null)
  const editorResizeRef = useRef<{ startY: number; startHeight: number } | null>(null)

  const watchedBodyType = Form.useWatch('bodyType', caseForm)
  const watchedQuery = Form.useWatch('query', caseForm)

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

  const { collectionQuery, casesQuery, requirementId, requirementQuery, sprintId, sprintQuery, projectId, environmentsQuery, environments, selectedEnvironment, resolvedEnvironmentId, environmentVarsQuery, environmentVars, activeCaseId, selectedCaseDetailQuery } = useApiCollectionData({ collectionId, selectedEnvironmentId, selectedCaseId })

  const { can } = useProjectAccess(projectId ?? '')

  const cases = casesQuery.data ?? EMPTY_API_CASES
  const { assertRuleModalOpen, setAssertRuleModalOpen, extractRuleModalOpen, setExtractRuleModalOpen, editingAssertRule, setEditingAssertRule, editingExtractRule, setEditingExtractRule, assertRuleForm, extractRuleForm, watchedAssertSource, watchedAssertComparator, watchedExtractSource, saveAssertRuleMutation, deleteAssertRuleMutation, toggleAssertRuleMutation, saveExtractRuleMutation, deleteExtractRuleMutation, toggleExtractRuleMutation, openCreateAssertRule, openEditAssertRule, openCreateExtractRule, openEditExtractRule, assertRulesQuery, extractRulesQuery, assertRules, extractRules } = useApiRuleEditing({ activeCaseId })

  const { runResult, setRunResult, setActiveApiCaseRunId, runResultView, setRunResultView, collectionRunReportOpen, setCollectionRunReportOpen, collectionRunHistoryOpen, setCollectionRunHistoryOpen, selectedCollectionRunId, setSelectedCollectionRunId, setActivePollingCollectionRunId, loadingCollectionRunHistoryId, setLoadingCollectionRunHistoryId, refreshingCollectionRunReport, setRefreshingCollectionRunReport, collectionRunReportView, setCollectionRunReportView, expandedCollectionRunItemIds, setExpandedCollectionRunItemIds, collectionRunItemViews, setCollectionRunItemViews, previousApiCaseRunStatusRef, previousActiveRunStatusRef, collectionRunHistoryQuery, activeCollectionRunQuery, collectionRunReportQuery, runApiCaseMutation, runApiCollectionMutation } = useApiExecution({ collectionId })

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
  }, [caseForm, collectionId, previousApiCaseRunStatusRef, setActiveApiCaseRunId, setRunResult, setRunResultView])

  useEffect(() => {
    setSelectedCollectionRunId('')
    setCollectionRunReportOpen(false)
    setCollectionRunHistoryOpen(false)
    setActivePollingCollectionRunId('')
    previousActiveRunStatusRef.current = ''
  }, [collectionId, previousActiveRunStatusRef, setActivePollingCollectionRunId, setCollectionRunHistoryOpen, setCollectionRunReportOpen, setSelectedCollectionRunId])

  const { createCaseMutation, updateCaseMutation, deleteCaseMutation, reorderCasesMutation } = useApiCaseEditing({ setEditingCase, setSelectedCaseId, caseForm, collectionId, caseOrderIds, cases, setDraftCaseValues, caseOrderRollbackRef, setCaseOrderIds, editingCase, setDraggingCaseId })

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

  useEffect(() => {
    ensureQueryTrailingRow(watchedQuery)
  }, [ensureQueryTrailingRow, watchedQuery])

  useEffect(() => {
    setRunResult(null)
    setRunResultView('response')
    setAssertRuleModalOpen(false)
    setExtractRuleModalOpen(false)
    setEditingAssertRule(null)
    setEditingExtractRule(null)
    assertRuleForm.resetFields()
    extractRuleForm.resetFields()
  }, [assertRuleForm, extractRuleForm, selectedCaseId, setAssertRuleModalOpen, setEditingAssertRule, setEditingExtractRule, setExtractRuleModalOpen, setRunResult, setRunResultView])

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

  function handleCompressBodyJson() {
    bodyJsonEditorRef.current?.compressDocument()
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

  const runResultStatus = runResult?.status ?? (runResult ? (runResult.success ? 'success' : 'failed') : undefined)
  const isApiCaseRunInProgress = isApiRunPollingStatus(runResultStatus)
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

  function handleDiscardDraft() {
    setDraftCaseValues(null)
    const fallbackCase = filteredCases[0] ?? null
    if (fallbackCase) {
      setSelectedCaseId(getCaseId(fallbackCase))
      return
    }
    setSelectedCaseId('')
    setEditingCase(null)
    resetCaseForm()
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
    <div className="workbench-page api-collection-detail-page api-collection-workbench-page tp-surface">
      <div className="api-automation-content">
        <div className="page-frame api-collection-workbench tp-board">
          {collectionQuery.error ? <Alert showIcon type="error" title={getErrorMessage(collectionQuery.error)} /> : null}
          {casesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}
          {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getErrorMessage(selectedCaseDetailQuery.error)} /> : null}
          {requirementQuery.error ? <Alert showIcon type="error" title={getErrorMessage(requirementQuery.error)} /> : null}
          {sprintQuery.error ? <Alert showIcon type="error" title={getErrorMessage(sprintQuery.error)} /> : null}
          {assertRulesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(assertRulesQuery.error)} /> : null}
          {extractRulesQuery.error ? <Alert showIcon type="error" title={getErrorMessage(extractRulesQuery.error)} /> : null}

          <ApiCollectionToolbar
            collectionName={collectionQuery.data?.name ?? '-'}
            requirementName={requirementQuery.data?.name ?? requirementId ?? '-'}
            sprintName={sprintQuery.data?.name ?? sprintId ?? '-'}
            updatedAt={collectionQuery.data ? formatTime(pickUpdatedAt(collectionQuery.data)) : '-'}
            environmentBaseUrl={selectedEnvironment?.baseUrl ?? ''}
            runHistoryCount={collectionRunHistory.length}
            runningCollection={runApiCollectionMutation.isPending}
            runDisabled={!resolvedEnvironmentId || cases.length === 0}
            onBack={() => navigate('/api-automation')}
            onOpenRunHistory={() => setCollectionRunHistoryOpen(true)}
            onRunCollection={handleRunCollection}
          />

          <div className="api-wb-cols">
            <ApiCaseExplorer
              cases={sidebarCases}
              selectedCaseId={selectedCaseId}
              loading={casesQuery.isLoading}
              totalCaseCount={cases.length}
              search={caseSearch}
              canReorder={canReorder}
              draggingCaseId={draggingCaseId}
              onSearchChange={setCaseSearch}
              onSelectCase={setSelectedCaseId}
              onCreateCase={openCreateDrawer}
              onImportCases={openCaseImportModal}
              onDeleteCase={(caseId) => deleteCaseMutation.mutate(caseId)}
              onDiscardDraft={handleDiscardDraft}
              onDragStart={handleCaseDragStart}
              onDrop={handleCaseDrop}
              onDragEnd={() => setDraggingCaseId(null)}
            />

            <section className="api-wb-editor-panel">
              <div className="api-wb-editor-shell" ref={editorLayoutRef}>
                <div className="api-wb-editor-main" style={runResult ? { flexBasis: `${editorTopHeight}px` } : undefined}>
                  <div className="api-wb-editor-main-scroll">
                    <ApiCaseEditor caseForm={caseForm} isCreatingCase={isCreatingCase} setDraftCaseValues={setDraftCaseValues} getCompleteCaseFormValues={getCompleteCaseFormValues} createCaseMutation={createCaseMutation} editingCase={editingCase} activeCaseId={activeCaseId} updateCaseMutation={updateCaseMutation} pathInputRef={pathInputRef} runApiCaseMutation={runApiCaseMutation} isApiCaseRunInProgress={isApiCaseRunInProgress} isSelectedCaseReady={isSelectedCaseReady} handleSendRequest={handleSendRequest} watchedBodyType={watchedBodyType} environment={{ environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery }} templates={{ setEnvVarInputRef, renderEnvVarPicker, insertTemplateText, bodyJsonEditorRef, insertTemplateTextIntoJson, handleFormatBodyJson, handleCompressBodyJson }} rules={{ postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation }} />
                  </div>
                </div>
                {runResult ? (
                  <>
                    <div
                      className={`api-wb-splitter${isResizingEditor ? ' resizing' : ''}`}
                      role="separator"
                      aria-orientation="horizontal"
                      aria-label="调整请求编辑区与运行结果的高度"
                      onPointerDown={handleEditorSplitterPointerDown}
                    >
                      <span className="api-wb-splitter-line" />
                      <span className="api-wb-splitter-grip">⋯</span>
                    </div>
                    <div className="api-wb-console-pane">
                      <div className="api-wb-console-scroll">
                        <ApiCaseRunConsole
                          result={runResult}
                          environmentName={selectedEnvironment?.name ?? runResult.environmentId ?? '-'}
                          view={runResultView}
                          onViewChange={(value) => setRunResultView(value)}
                        />
                      </div>
                    </div>
                  </>
                ) : null}
              </div>
            </section>
          </div>
        </div>
      </div>

      <ApiCaseImportModal caseImportModalOpen={caseImportModalOpen} closeCaseImportModal={closeCaseImportModal} importApiCasesMutation={importApiCasesMutation} handleImportApiCases={handleImportApiCases} caseImportMode={caseImportMode} setCaseImportMode={setCaseImportMode} setImportYamlFile={setImportYamlFile} importYamlText={importYamlText} setImportYamlText={setImportYamlText} />

      <ApiCollectionRunHistory collectionRunHistoryOpen={collectionRunHistoryOpen} setCollectionRunHistoryOpen={setCollectionRunHistoryOpen} collectionRunHistoryQuery={collectionRunHistoryQuery} collectionRunHistory={collectionRunHistory} loadingCollectionRunHistoryId={loadingCollectionRunHistoryId} environments={environments} handleOpenCollectionRunHistoryItem={handleOpenCollectionRunHistoryItem} />

      <ApiCollectionRunReportModal collectionRunReportOpen={collectionRunReportOpen} setCollectionRunReportOpen={setCollectionRunReportOpen} setSelectedCollectionRunId={setSelectedCollectionRunId} collectionRunReportQuery={collectionRunReportQuery} collectionRunReport={collectionRunReport} environments={environments} handleExportCollectionRunReportHtml={handleExportCollectionRunReportHtml} handleRefreshCollectionRunReport={handleRefreshCollectionRunReport} refreshingCollectionRunReport={refreshingCollectionRunReport} selectedCollectionRunId={selectedCollectionRunId} collectionRunReportView={collectionRunReportView} setCollectionRunReportView={setCollectionRunReportView} orderedCollectionRunItems={orderedCollectionRunItems} expandedCollectionRunItemIds={expandedCollectionRunItemIds} collectionRunItemViews={collectionRunItemViews} toggleCollectionRunItem={toggleCollectionRunItem} handleCollectionRunItemViewChange={handleCollectionRunItemViewChange} selectedCollectionRunSummary={selectedCollectionRunSummary} />

      <ApiAssertRuleEditor assertRuleModalOpen={assertRuleModalOpen} editingAssertRule={editingAssertRule} setAssertRuleModalOpen={setAssertRuleModalOpen} setEditingAssertRule={setEditingAssertRule} assertRuleForm={assertRuleForm} saveAssertRuleMutation={saveAssertRuleMutation} watchedAssertSource={watchedAssertSource} watchedAssertComparator={watchedAssertComparator} />

      <ApiExtractRuleEditor extractRuleModalOpen={extractRuleModalOpen} editingExtractRule={editingExtractRule} setExtractRuleModalOpen={setExtractRuleModalOpen} setEditingExtractRule={setEditingExtractRule} extractRuleForm={extractRuleForm} saveExtractRuleMutation={saveExtractRuleMutation} watchedExtractSource={watchedExtractSource} />

      {renderEnvVarPickerModal()}
    </div>
  )}</ProjectAccessScope>)
}
