import { ApiAssertRuleEditor } from '@/features/api-automation/components/ApiAssertRuleEditor'
import { ApiCaseEditor } from '@/features/api-automation/components/ApiCaseEditor'
import { ApiCaseImportModal } from '@/features/api-automation/components/ApiCaseImportModal'
import { ApiCollectionRunHistory } from '@/features/api-automation/components/ApiCollectionRunHistory'
import { ApiCollectionRunReportModal } from '@/features/api-automation/components/ApiCollectionRunReport'
import { ApiExtractRuleEditor } from '@/features/api-automation/components/ApiExtractRuleEditor'
import { Text, isApiRunPollingStatus, isYamlFileName, type CaseImportMode } from '@/features/api-automation/utils/detailView'
import { renderRunResultContent } from '@/features/api-automation/utils/renderApiRunResult'
import { useApiCaseEditing } from '../hooks/useApiCaseEditing'
import { useApiCollectionData } from '../hooks/useApiCollectionData'
import { useApiExecution } from '../hooks/useApiExecution'
import { useApiRuleEditing } from '../hooks/useApiRuleEditing'

import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
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
import { ArrowLeftOutlined, CheckOutlined, CodeSandboxOutlined, FunctionOutlined, SearchOutlined, SendOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { InputRef } from 'antd'
import { Alert, Button, Card, Empty, Form, Input, Modal, Popconfirm, Segmented, Tag } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  DRAFT_CASE_ID,
  ENV_VAR_TOKEN_PREFIX,
  ENV_VAR_TOKEN_SUFFIX,
  MIN_EDITOR_RESULT_HEIGHT,
  MIN_EDITOR_TOP_HEIGHT,
  builtinTemplateFunctions,
  methodTagColor,
  runResultViewOptions,
  type EnvVarPickerMode,
  type RunResultView
} from '../config/collectionConfig'
import {
  EMPTY_API_CASES,
  buildApiCaseUpdatePayload,
  buildCaseFormValues,
  createDefaultCaseFormValues,
  getCaseDisplayPath,
  getCaseId,
  moveArrayItem,
  sortCasesByOrderNo,
  type ApiCaseFormValues
} from '../utils/apiCaseEditor'
import { buildCollectionRunReportHtml, getExecutionStatusMeta, sanitizeFileName } from '../utils/collectionRunReport'

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
  const watchedHeaders = Form.useWatch('headers', caseForm)

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
                      <ApiCaseEditor caseForm={caseForm} isCreatingCase={isCreatingCase} setDraftCaseValues={setDraftCaseValues} getCompleteCaseFormValues={getCompleteCaseFormValues} createCaseMutation={createCaseMutation} editingCase={editingCase} activeCaseId={activeCaseId} updateCaseMutation={updateCaseMutation} pathInputRef={pathInputRef} runApiCaseMutation={runApiCaseMutation} isApiCaseRunInProgress={isApiCaseRunInProgress} isSelectedCaseReady={isSelectedCaseReady} handleSendRequest={handleSendRequest} watchedBodyType={watchedBodyType} environment={{ environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery }} templates={{ setEnvVarInputRef, renderEnvVarPicker, insertTemplateText, bodyJsonEditorRef, insertTemplateTextIntoJson, handleFormatBodyJson }} rules={{ postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation }} />
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

      <ApiCaseImportModal caseImportModalOpen={caseImportModalOpen} closeCaseImportModal={closeCaseImportModal} importApiCasesMutation={importApiCasesMutation} handleImportApiCases={handleImportApiCases} caseImportMode={caseImportMode} setCaseImportMode={setCaseImportMode} setImportYamlFile={setImportYamlFile} importYamlText={importYamlText} setImportYamlText={setImportYamlText} />

      <ApiCollectionRunHistory collectionRunHistoryOpen={collectionRunHistoryOpen} setCollectionRunHistoryOpen={setCollectionRunHistoryOpen} collectionRunHistoryQuery={collectionRunHistoryQuery} collectionRunHistory={collectionRunHistory} loadingCollectionRunHistoryId={loadingCollectionRunHistoryId} environments={environments} handleOpenCollectionRunHistoryItem={handleOpenCollectionRunHistoryItem} />

      <ApiCollectionRunReportModal collectionRunReportOpen={collectionRunReportOpen} setCollectionRunReportOpen={setCollectionRunReportOpen} setSelectedCollectionRunId={setSelectedCollectionRunId} collectionRunReportQuery={collectionRunReportQuery} collectionRunReport={collectionRunReport} environments={environments} handleExportCollectionRunReportHtml={handleExportCollectionRunReportHtml} handleRefreshCollectionRunReport={handleRefreshCollectionRunReport} refreshingCollectionRunReport={refreshingCollectionRunReport} selectedCollectionRunId={selectedCollectionRunId} collectionRunReportView={collectionRunReportView} setCollectionRunReportView={setCollectionRunReportView} orderedCollectionRunItems={orderedCollectionRunItems} expandedCollectionRunItemIds={expandedCollectionRunItemIds} collectionRunItemViews={collectionRunItemViews} toggleCollectionRunItem={toggleCollectionRunItem} handleCollectionRunItemViewChange={handleCollectionRunItemViewChange} selectedCollectionRunSummary={selectedCollectionRunSummary} />

      <ApiAssertRuleEditor assertRuleModalOpen={assertRuleModalOpen} editingAssertRule={editingAssertRule} setAssertRuleModalOpen={setAssertRuleModalOpen} setEditingAssertRule={setEditingAssertRule} assertRuleForm={assertRuleForm} saveAssertRuleMutation={saveAssertRuleMutation} watchedAssertSource={watchedAssertSource} watchedAssertComparator={watchedAssertComparator} />

      <ApiExtractRuleEditor extractRuleModalOpen={extractRuleModalOpen} editingExtractRule={editingExtractRule} setExtractRuleModalOpen={setExtractRuleModalOpen} setEditingExtractRule={setEditingExtractRule} extractRuleForm={extractRuleForm} saveExtractRuleMutation={saveExtractRuleMutation} watchedExtractSource={watchedExtractSource} />

      {renderEnvVarPickerModal()}
    </div>
  )}</ProjectAccessScope>)
}
