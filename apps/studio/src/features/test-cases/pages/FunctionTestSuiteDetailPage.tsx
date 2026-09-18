import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { FunctionCaseContentEditor } from '../components/FunctionCaseContentEditor'
import { priorityColor } from '../utils/casePriority'
import { ArrowLeftOutlined, FlagOutlined, ProfileOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons'
import { Alert, AutoComplete, Button, Checkbox, Empty, Form, Input, InputNumber, Popconfirm, Segmented, Select, Tag, Tooltip, Typography, Upload } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { message } from '@/shared/utils/feedback'
import { ApiError, api, type CreateFunctionTestCasePayload, type FunctionTestCase } from '@/services/api'
import {
  formatTime,
  getErrorMessage,
  normalizeFunctionTestCaseId,
  normalizeFunctionTestSuiteId,
  pickCreatedAt,
  pickUpdatedAt,
} from '@/utils/format'
import '@/features/test-cases/styles/index.css'

const { Text, Title } = Typography

type FunctionTestCaseFormValues = CreateFunctionTestCasePayload
type CaseImportMode = 'upload' | 'editor'
type ZentaoImportFormValues = {
  productId: number
  moduleId?: number
}

const DRAFT_CASE_ID = '__draft_function_test_case__'
const priorityOptions = ['P0', 'P1', 'P2', 'P3'].map((value) => ({ label: value, value }))
const caseTypeOptions = ['功能测试', '异常测试', '边界测试', '流程测试', '兼容测试', '安全测试'].map((value) => ({ label: value, value }))

function compactText(value?: string) {
  return value?.trim() || '-'
}

function formatFunctionalCaseNavTitle(title?: string, module?: string) {
  const originalTitle = compactText(title)
  const leadingSegments: string[] = []
  let restTitle = originalTitle

  while (restTitle.startsWith('【')) {
    const match = /^【([^】]+)】\s*/.exec(restTitle)
    if (!match) break
    leadingSegments.push(match[1])
    restTitle = restTitle.slice(match[0].length).trim()
  }

  if (leadingSegments.length === 0) return originalTitle

  const moduleText = module?.trim() ?? ''
  const visibleSegments = leadingSegments.filter((segment, index) => !(index === 0 && moduleText.includes(segment)))
  const body = restTitle.trim()

  if (visibleSegments.length === 0) return body || originalTitle
  return `${visibleSegments.join(' / ')}${body ? `：${body}` : ''}`
}

function formatFunctionalCaseTypeLabel(caseType?: string) {
  return caseType?.replace(/测试$/u, '').trim()
}

function isJsonFileName(fileName: string) {
  return /\.json$/i.test(fileName.trim())
}

function sortFunctionCases(cases: FunctionTestCase[]) {
  return [...cases].sort((left, right) => {
    const leftOrder = left.orderNo ?? Number.MAX_SAFE_INTEGER
    const rightOrder = right.orderNo ?? Number.MAX_SAFE_INTEGER
    if (leftOrder !== rightOrder) return leftOrder - rightOrder

    const leftTime = new Date(pickCreatedAt(left) ?? '').getTime()
    const rightTime = new Date(pickCreatedAt(right) ?? '').getTime()
    return (Number.isNaN(leftTime) ? 0 : leftTime) - (Number.isNaN(rightTime) ? 0 : rightTime)
  })
}

function createDefaultCaseFormValues(orderNo = 1): FunctionTestCaseFormValues {
  return {
    title: '',
    module: '',
    priority: 'P2',
    caseType: '功能测试',
    content: { preconditions: [], steps: [] },
    orderNo,
  }
}

function buildCaseFormValues(testCase?: Partial<FunctionTestCase>): FunctionTestCaseFormValues {
  return {
    ...createDefaultCaseFormValues(testCase?.orderNo ?? 1),
    title: testCase?.title ?? '',
    module: testCase?.module ?? '',
    priority: testCase?.priority ?? 'P2',
    caseType: testCase?.caseType ?? '功能测试',
    content: testCase?.content
      ? { preconditions: [...testCase.content.preconditions], steps: testCase.content.steps.map((step) => ({ ...step })) }
      : {
          preconditions: testCase?.preconditions ? [testCase.preconditions] : [],
          steps: testCase?.steps || testCase?.expectedResults
            ? [{ action: testCase.steps ?? '', expected: testCase.expectedResults ?? '' }]
            : [],
        },
    orderNo: testCase?.orderNo ?? 1,
  }
}

function getFunctionCaseErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 3301) return '功能测试用例不存在'
    if (error.code === 3302) return '同一个功能测试集下用例标题不能重复'
  }

  return getErrorMessage(error)
}

function getZentaoImportErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    const errorText = `${error.message} ${error.code}`.toLowerCase()
    if (/绑定|禅道|zentao|binding/.test(errorText)) {
      return '导入失败：请先完成项目和迭代的禅道绑定'
    }
  }

  return getFunctionCaseErrorMessage(error)
}

export function FunctionTestSuiteDetailPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const personalZentao = usePersonalConnectionChoice('zentao')
  const { suiteId = '' } = useParams()
  const [caseSearch, setCaseSearch] = useState('')
  const [selectedCaseId, setSelectedCaseId] = useState('')
  const [editingCase, setEditingCase] = useState<FunctionTestCase | null>(null)
  const [draftCaseValues, setDraftCaseValues] = useState<FunctionTestCaseFormValues | null>(null)
  const [caseImportModalOpen, setCaseImportModalOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importJsonFile, setImportJsonFile] = useState<File | null>(null)
  const [importJsonText, setImportJsonText] = useState('')
  const [zentaoImportModalOpen, setZentaoImportModalOpen] = useState(false)
  const [selectedZentaoCaseIds, setSelectedZentaoCaseIds] = useState<string[]>([])
  const [form] = Form.useForm<FunctionTestCaseFormValues>()
  const [zentaoImportForm] = Form.useForm<ZentaoImportFormValues>()
  const sidebarItemRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const backToFunctionalListUrl = useMemo(() => {
    const nextSearchParams = new URLSearchParams(searchParams)
    nextSearchParams.set('tab', 'functional')
    return `/testing?${nextSearchParams.toString()}`
  }, [searchParams])

  const suiteQuery = useQuery({
    queryKey: ['functionTestSuite', suiteId],
    queryFn: () => api.getFunctionTestSuite(suiteId),
    enabled: Boolean(suiteId),
  })
  const casesQuery = useQuery({
    queryKey: ['functionTestCases', suiteId],
    queryFn: () => api.getFunctionTestCases(suiteId),
    enabled: Boolean(suiteId),
  })

  const requirementId = suiteQuery.data?.requirementId ?? suiteQuery.data?.requirement_id
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

  const caseTotal = casesQuery.data?.total ?? 0
  const orderedCases = useMemo(() => sortFunctionCases(casesQuery.data?.items ?? []), [casesQuery.data?.items])
  const filteredCases = useMemo(() => {
    const keyword = caseSearch.trim().toLowerCase()
    if (!keyword) return orderedCases

    return orderedCases.filter((item) =>
      [item.title, item.module, item.priority, item.caseType, item.preconditions, item.steps, item.expectedResults]
        .filter(Boolean)
        .some((value) => value!.toLowerCase().includes(keyword)),
    )
  }, [caseSearch, orderedCases])

  const isCreatingCase = selectedCaseId === DRAFT_CASE_ID
  const activeCaseId = !isCreatingCase ? selectedCaseId : ''
  const selectedCaseDetailQuery = useQuery({
    queryKey: ['functionTestCase', activeCaseId],
    queryFn: () => api.getFunctionTestCase(activeCaseId),
    enabled: Boolean(activeCaseId),
    refetchOnWindowFocus: false,
  })

  const sidebarCases = useMemo(() => {
    const items = filteredCases.map((item) => ({
      id: normalizeFunctionTestCaseId(item),
      title: item.title,
      module: item.module,
      priority: item.priority,
      caseType: item.caseType,
      orderNo: item.orderNo,
      isDraft: false,
      raw: item,
    }))

    if (!isCreatingCase) return items

    return [
      {
        id: DRAFT_CASE_ID,
        title: draftCaseValues?.title?.trim() || '未命名用例',
        module: draftCaseValues?.module,
        priority: draftCaseValues?.priority,
        caseType: draftCaseValues?.caseType,
        orderNo: draftCaseValues?.orderNo,
        isDraft: true,
        raw: null,
      },
      ...items,
    ]
  }, [draftCaseValues, filteredCases, isCreatingCase])

  const normalizedEditingCaseId = editingCase ? normalizeFunctionTestCaseId(editingCase) : ''
  const selectedZentaoCaseIdSet = useMemo(() => new Set(selectedZentaoCaseIds), [selectedZentaoCaseIds])
  const savedCaseIds = useMemo(
    () => orderedCases.map((item) => normalizeFunctionTestCaseId(item)).filter(Boolean),
    [orderedCases],
  )

  const selectedImportCaseCount = selectedZentaoCaseIds.length
  const zentaoImportTargetCount = selectedImportCaseCount || caseTotal
  const allSavedCasesSelected = savedCaseIds.length > 0 && selectedZentaoCaseIds.length === savedCaseIds.length
  const partialSavedCasesSelected = selectedZentaoCaseIds.length > 0 && selectedZentaoCaseIds.length < savedCaseIds.length

  function validateUniqueTitle(_: unknown, value?: string) {
    const nextTitle = value?.trim().toLowerCase()
    if (!nextTitle) return Promise.resolve()

    const duplicated = orderedCases.some((item) => {
      const itemId = normalizeFunctionTestCaseId(item)
      if (normalizedEditingCaseId && itemId === normalizedEditingCaseId) return false
      return item.title.trim().toLowerCase() === nextTitle
    })

    if (duplicated) {
      return Promise.reject(new Error('同一个功能测试集下用例标题不能重复'))
    }

    return Promise.resolve()
  }

  function getCompleteCaseFormValues() {
    const currentValues = form.getFieldsValue(true) as Partial<FunctionTestCaseFormValues>
    return {
      ...createDefaultCaseFormValues(currentValues.orderNo ?? draftCaseValues?.orderNo ?? orderedCases.length + 1),
      ...currentValues,
    } satisfies FunctionTestCaseFormValues
  }

  function syncCaseDetailState(testCase: FunctionTestCase) {
    const caseId = normalizeFunctionTestCaseId(testCase)
    if (!caseId) return

    setSelectedCaseId(caseId)
    setEditingCase(testCase)
    setDraftCaseValues(null)
    form.setFieldsValue(buildCaseFormValues(testCase))
    queryClient.setQueryData(['functionTestCase', caseId], testCase)
  }

  function openCreateCase() {
    const defaultValues = createDefaultCaseFormValues(orderedCases.length + 1)
    setSelectedCaseId(DRAFT_CASE_ID)
    setEditingCase(null)
    setDraftCaseValues(defaultValues)
    form.setFieldsValue(defaultValues)
  }

  function handleSelectSavedCase(testCase: FunctionTestCase) {
    const caseId = normalizeFunctionTestCaseId(testCase)
    if (!caseId) return

    setSelectedCaseId(caseId)
    setEditingCase(testCase)
    setDraftCaseValues(null)
    form.setFieldsValue(buildCaseFormValues(testCase))
  }

  function handleSelectSidebarCase(item: (typeof sidebarCases)[number]) {
    if (item.isDraft) {
      openCreateCase()
      return
    }
    if (item.raw) {
      handleSelectSavedCase(item.raw)
    }
  }

  function handleSidebarCaseKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return

    event.preventDefault()
    const nextIndex = event.key === 'ArrowDown'
      ? Math.min(sidebarCases.length - 1, index + 1)
      : Math.max(0, index - 1)
    const nextItem = sidebarCases[nextIndex]
    if (!nextItem) return

    handleSelectSidebarCase(nextItem)
    window.requestAnimationFrame(() => {
      sidebarItemRefs.current[nextItem.id]?.focus()
      sidebarItemRefs.current[nextItem.id]?.scrollIntoView({ block: 'nearest' })
    })
  }

  function openCaseImportModal() {
    setCaseImportModalOpen(true)
  }

  function openZentaoImportModal() {
    zentaoImportForm.setFieldsValue({
      productId: 1,
      moduleId: 0,
    })
    setZentaoImportModalOpen(true)
  }

  function closeCaseImportModal() {
    if (importFunctionCasesMutation.isPending) return
    setCaseImportModalOpen(false)
    setCaseImportMode('upload')
    setImportJsonFile(null)
    setImportJsonText('')
  }

  function handleImportFunctionCases() {
    if (!suiteId) return

    if (caseImportMode === 'upload') {
      if (!importJsonFile) {
        message.warning('请上传 JSON 文件')
        return
      }
      if (!isJsonFileName(importJsonFile.name)) {
        message.warning('仅支持 .json 文件')
        return
      }

      importFunctionCasesMutation.mutate({
        file: importJsonFile,
        filename: importJsonFile.name,
      })
      return
    }

    const jsonContent = importJsonText.trim()
    if (!jsonContent) {
      message.warning('请输入 JSON 内容')
      return
    }

    try {
      JSON.parse(jsonContent)
    } catch {
      message.warning('JSON 格式不正确')
      return
    }

    const generatedFileName = `function-suite-${suiteId || 'cases'}.json`
    importFunctionCasesMutation.mutate({
      file: new File([jsonContent], generatedFileName, { type: 'application/json' }),
      filename: generatedFileName,
    })
  }

  function handleToggleZentaoCase(caseId: string, checked: boolean) {
    setSelectedZentaoCaseIds((current) => {
      if (checked) return current.includes(caseId) ? current : [...current, caseId]
      return current.filter((item) => item !== caseId)
    })
  }

  function handleToggleAllZentaoCases(checked: boolean) {
    setSelectedZentaoCaseIds(checked ? savedCaseIds : [])
  }

  function closeZentaoImportModal() {
    if (importZentaoTestCasesMutation.isPending) return
    setZentaoImportModalOpen(false)
  }

  async function handleImportZentaoTestCases() {
    if (!suiteId) return
    if (orderedCases.length === 0) {
      message.warning('当前测试集还没有可导入的用例')
      return
    }

    const values = await zentaoImportForm.validateFields()
    importZentaoTestCasesMutation.mutate({
      productId: values.productId,
      moduleId: values.moduleId ?? 0,
      caseIds: selectedZentaoCaseIds.length > 0 ? selectedZentaoCaseIds : undefined,
    })
  }

  useEffect(() => {
    setCaseSearch('')
    setSelectedCaseId('')
    setEditingCase(null)
    setDraftCaseValues(null)
    setSelectedZentaoCaseIds([])
    form.setFieldsValue(createDefaultCaseFormValues())
  }, [form, suiteId])

  useEffect(() => {
    setSelectedZentaoCaseIds((current) => current.filter((caseId) => savedCaseIds.includes(caseId)))
  }, [savedCaseIds])

  useEffect(() => {
    if (isCreatingCase) return

    if (orderedCases.length === 0) {
      setSelectedCaseId('')
      setEditingCase(null)
      form.setFieldsValue(createDefaultCaseFormValues())
      return
    }

    const selectedExists = orderedCases.some((item) => normalizeFunctionTestCaseId(item) === selectedCaseId)
    if (selectedExists) return

    const firstCase = orderedCases[0]
    const firstCaseId = normalizeFunctionTestCaseId(firstCase)
    if (!firstCaseId) return

    setSelectedCaseId(firstCaseId)
    setEditingCase(firstCase)
    form.setFieldsValue(buildCaseFormValues(firstCase))
  }, [form, isCreatingCase, orderedCases, selectedCaseId])

  useEffect(() => {
    if (!selectedCaseDetailQuery.data || !activeCaseId || selectedCaseId !== activeCaseId) return
    if (editingCase && normalizeFunctionTestCaseId(editingCase) === activeCaseId) return
    setEditingCase(selectedCaseDetailQuery.data)
    form.setFieldsValue(buildCaseFormValues(selectedCaseDetailQuery.data))
  }, [activeCaseId, editingCase, form, selectedCaseDetailQuery.data, selectedCaseId])

  const saveCaseMutation = useMutation({
    mutationFn: (values: FunctionTestCaseFormValues) => {
      if (isCreatingCase || !editingCase) {
        if (!suiteId) throw new Error('未获取到功能测试集 ID')
        return api.createFunctionTestCase(suiteId, values)
      }

      const caseId = normalizeFunctionTestCaseId(editingCase)
      if (!caseId) throw new Error('未获取到功能测试用例 ID')
      return api.updateFunctionTestCase(caseId, values)
    },
    onSuccess: (testCase) => {
      message.success(isCreatingCase ? '功能测试用例已创建' : '功能测试用例已更新')
      syncCaseDetailState(testCase)
      queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 3302) {
        form.setFields([{ name: 'title', errors: ['同一个功能测试集下用例标题不能重复'] }])
      }
      if (error instanceof ApiError && error.code === 3301) {
        queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
        queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      }
      message.error(getFunctionCaseErrorMessage(error))
    },
  })

  const importFunctionCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) => api.importFunctionTestCases(suiteId, file, filename),
    onSuccess: (result) => {
      const importedCount = result.importedCaseCount ?? result.imported_case_count ?? result.importedCount ?? result.imported_count ?? 0
      message.success(`导入成功：${importedCount} 条用例`)
      setCaseImportModalOpen(false)
      setCaseImportMode('upload')
      setImportJsonFile(null)
      setImportJsonText('')
      queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
    },
    onError: (error) => {
      message.error(getFunctionCaseErrorMessage(error))
    },
  })

  const importZentaoTestCasesMutation = useMutation({
    mutationFn: async (values: ZentaoImportFormValues & { caseIds?: string[] }) => api.importFunctionTestCasesToZentao(suiteId, { ...values, connectionId: await personalZentao.forZentaoRequirement(sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? '', requirementId ?? '') }),
    onSuccess: (result) => {
      const importedCount = result.importedCaseCount ?? result.imported_case_count ?? result.items?.length ?? 0
      message.success(`已导入禅道：${importedCount} 条用例`)
      setZentaoImportModalOpen(false)
      setSelectedZentaoCaseIds([])
      zentaoImportForm.resetFields()
    },
    onError: (error) => {
      message.error(getZentaoImportErrorMessage(error))
    },
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deleteFunctionTestCase(caseId),
    onSuccess: (_data, caseId) => {
      message.success('功能测试用例已删除')
      queryClient.removeQueries({ queryKey: ['functionTestCase', caseId], exact: true })
      queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })

      if (selectedCaseId !== caseId) return

      const remainingCases = orderedCases.filter((item) => normalizeFunctionTestCaseId(item) !== caseId)
      const nextCase = remainingCases[0]
      if (!nextCase) {
        setSelectedCaseId('')
        setEditingCase(null)
        form.setFieldsValue(createDefaultCaseFormValues())
        return
      }

      handleSelectSavedCase(nextCase)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 3301) {
        queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
        queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      }
      message.error(getFunctionCaseErrorMessage(error))
    },
  })

  const batchDeleteMutation = useMutation({
    mutationFn: (caseIds: string[]) => api.batchDeleteFunctionTestCases(suiteId, caseIds),
    onSuccess: ({ deletedIds, deletedCount }) => {
      const deleted = new Set(deletedIds)
      setSelectedZentaoCaseIds((current) => current.filter((id) => !deleted.has(id)))
      for (const id of deletedIds) {
        queryClient.removeQueries({ queryKey: ['functionTestCase', id], exact: true })
      }
      queryClient.invalidateQueries({ queryKey: ['functionTestCases', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['functionTestSuites'] })
      if (deleted.has(selectedCaseId)) {
        const nextCase = orderedCases.find((item) => !deleted.has(normalizeFunctionTestCaseId(item)))
        if (nextCase) {
          handleSelectSavedCase(nextCase)
        } else {
          setSelectedCaseId('')
          setEditingCase(null)
          form.setFieldsValue(createDefaultCaseFormValues())
        }
      }
      message.success(`已删除 ${deletedCount} 条功能测试用例`)
    },
    onError: (error) => message.error(getFunctionCaseErrorMessage(error)),
  })

  const suite = suiteQuery.data
  const suiteName = suite?.name || '功能测试集'
  const suiteKey = suite ? normalizeFunctionTestSuiteId(suite) : suiteId
  const currentCase = isCreatingCase ? null : editingCase

  return (<ProjectAccessScope projectId={sprintQuery.data?.projectId ?? sprintQuery.data?.project_id ?? ''}>{personalZentao.dialog}{(
    <>
    <div className="workbench-page api-collection-detail-page functional-suite-detail-page">
      <div className="api-automation-content">
        <div className="page-frame api-collection-detail-frame">
          <div className="api-collection-detail-layout functional-suite-detail-layout">
            {suiteQuery.error ? <Alert showIcon type="error" title={getFunctionCaseErrorMessage(suiteQuery.error)} /> : null}
            {casesQuery.error ? <Alert showIcon type="error" title={getFunctionCaseErrorMessage(casesQuery.error)} /> : null}
            {selectedCaseDetailQuery.error ? <Alert showIcon type="error" title={getFunctionCaseErrorMessage(selectedCaseDetailQuery.error)} /> : null}
            {requirementQuery.error ? <Alert showIcon type="error" title={getFunctionCaseErrorMessage(requirementQuery.error)} /> : null}
            {sprintQuery.error ? <Alert showIcon type="error" title={getFunctionCaseErrorMessage(sprintQuery.error)} /> : null}

            <aside className="workbench-panel api-case-sidebar functional-case-sidebar">
              <div className="panel-header api-case-sidebar-header">
                <div className="api-case-sidebar-title">
                  <Button
                    type="text"
                    icon={<ArrowLeftOutlined />}
                    className="api-case-back-button"
                    onClick={() => navigate(backToFunctionalListUrl)}
                    aria-label="返回功能测试列表"
                  />
                  <div className="api-case-sidebar-title-copy">
                    <Title level={5}>功能测试用例</Title>
                    <Text type="secondary" className="api-case-sidebar-count">
                      {caseTotal} 个用例
                    </Text>
                  </div>
                </div>
                <div className="api-case-sidebar-meta">
                  <Tooltip title="新建用例">
                    <ProjectActionButton action="write"
                      type="text"
                      className="action-btn-create"
                      shape="circle"
                      operation="create" iconOnly
                      aria-label="新建功能测试用例"
                      onClick={openCreateCase}
                      disabled={!suiteId}
                    />
                  </Tooltip>
                </div>
              </div>

              <div className="api-case-sidebar-toolbar">
                <Input
                  allowClear
                  value={caseSearch}
                  prefix={<SearchOutlined />}
                  placeholder="搜索用例名称 / 步骤 / 预期"
                  onChange={(event) => setCaseSearch(event.target.value)}
                />
                <ProjectActionButton action="execute" className="api-case-import-trigger" operation="upload" onClick={openCaseImportModal} disabled={!suiteId}>
                  用例导入
                </ProjectActionButton>
              </div>

              <div className="api-case-sidebar-scroll">
                {casesQuery.isLoading || suiteQuery.isLoading ? (
                  <div className="sprint-card-loading">
                    <Empty description="功能测试用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  </div>
                ) : (caseSearch ? sidebarCases.length === 0 : caseTotal === 0) ? (
                  <div className="ui-suite-case-empty-list">
                    <Empty description={caseSearch ? '没有匹配的功能测试用例' : '当前测试集还没有功能测试用例'}>
                      <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                        新建用例
                      </ProjectActionButton>
                    </Empty>
                  </div>
                ) : (
                  <div className="functional-case-nav-shell">
                    <div className="functional-case-selection-bar">
                      <Checkbox
                        disabled={batchDeleteMutation.isPending}
                        checked={allSavedCasesSelected}
                        indeterminate={partialSavedCasesSelected}
                        onChange={(event) => handleToggleAllZentaoCases(event.target.checked)}
                      >
                        选择用例
                      </Checkbox>
                      <span>{selectedImportCaseCount > 0 ? `已选 ${selectedImportCaseCount} 条` : '未选择用例'}</span>
                    </div>
                    <div className="api-case-nav-list functional-case-nav-list">
                      {sidebarCases.map((item, index) => {
                        const selected = item.id === selectedCaseId
                        const displayTitle = formatFunctionalCaseNavTitle(item.title, item.module)
                        const caseTypeLabel = formatFunctionalCaseTypeLabel(item.caseType)
                        const checkedForZentao = selectedZentaoCaseIdSet.has(item.id)

                        return (
                          <div key={item.id} className={`functional-case-nav-row${selected ? ' selected' : ''}`}>
                            {!item.isDraft ? (
                              <Checkbox
                                className="functional-case-nav-checkbox"
                                checked={checkedForZentao}
                                disabled={batchDeleteMutation.isPending}
                                aria-label={`选择用例：${item.title}`}
                                onClick={(event) => event.stopPropagation()}
                                onChange={(event) => handleToggleZentaoCase(item.id, event.target.checked)}
                              />
                            ) : (
                              <span className="functional-case-nav-checkbox-placeholder" />
                            )}
                            <button
                              ref={(node) => {
                                sidebarItemRefs.current[item.id] = node
                              }}
                              type="button"
                              className={`api-case-nav-item functional-case-nav-item${selected ? ' selected' : ''}`}
                              aria-current={selected ? 'true' : undefined}
                              onClick={() => handleSelectSidebarCase(item)}
                              onKeyDown={(event) => handleSidebarCaseKeyDown(event, index)}
                            >
                              <div className="api-case-nav-item-main functional-case-nav-item-main">
                                <div className="functional-case-nav-copy">
                                  <div className="functional-case-nav-title-row">
                                    <Tooltip title={item.title}>
                                      <span className="api-case-nav-item-name functional-case-nav-item-name">{displayTitle}</span>
                                    </Tooltip>
                                    {item.isDraft ? <Tag color="processing">草稿</Tag> : null}
                                  </div>
                                  <Tooltip title={compactText(item.module)}>
                                    <span className="api-case-nav-item-path functional-case-nav-item-path">{compactText(item.module)}</span>
                                  </Tooltip>
                                </div>
                              </div>
                              <div className="api-case-nav-item-actions functional-case-nav-item-actions">
                                <div className="api-case-nav-item-tags functional-case-nav-item-tags">
                                  {item.priority ? <Tag color={priorityColor(item.priority)}>{item.priority}</Tag> : null}
                                  {caseTypeLabel ? <Tag>{caseTypeLabel}</Tag> : null}
                                </div>
                              </div>
                            </button>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>
            </aside>

            <div className="api-case-workspace">
              <div className="api-detail-hover-panel api-collection-detail-panel functional-suite-detail-panel">
                <div className="api-detail-hover-bar">
                  <div className="api-detail-hover-bar-main">
                    <span className="api-detail-hover-title">测试集详情</span>
                    <span className="api-detail-hover-preview">
                      {suiteName} / {requirementQuery.data?.name ?? requirementId ?? '-'} / {sprintQuery.data?.name ?? sprintId ?? '-'}
                    </span>
                  </div>
                  <div className="api-detail-hover-bar-actions">
                    <Popconfirm
                      title={`确认删除选中的 ${selectedZentaoCaseIds.length} 条功能测试用例？`}
                      description="删除后不可恢复。"
                      okText="确认删除"
                      cancelText="取消"
                      okButtonProps={{ danger: true, loading: batchDeleteMutation.isPending }}
                      disabled={selectedZentaoCaseIds.length === 0 || batchDeleteMutation.isPending || deleteCaseMutation.isPending || saveCaseMutation.isPending}
                      onConfirm={() => {
                        if (selectedZentaoCaseIds.length === 0 || batchDeleteMutation.isPending) return
                        return batchDeleteMutation.mutateAsync([...selectedZentaoCaseIds]).catch(() => undefined)
                      }}
                    >
                      <ProjectActionButton action="write" operation="delete" danger
                        disabled={selectedZentaoCaseIds.length === 0 || deleteCaseMutation.isPending || saveCaseMutation.isPending}
                        loading={batchDeleteMutation.isPending}
                      >
                        批量删除{selectedZentaoCaseIds.length > 0 ? `（${selectedZentaoCaseIds.length}）` : ''}
                      </ProjectActionButton>
                    </Popconfirm>
                    <ProjectActionButton action="execute"
                      className="functional-case-zentao-import-trigger"
                      operation="upload"
                      onClick={openZentaoImportModal}
                      disabled={!suiteId || caseTotal === 0 || batchDeleteMutation.isPending}
                    >
                      导入禅道
                    </ProjectActionButton>
                    <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                      新建用例
                    </ProjectActionButton>
                  </div>
                </div>
                <div className="api-detail-hover-body">
                  <div className="functional-suite-context">
                    <div className="functional-suite-context-chip">
                      <span>测试集</span>
                      <strong title={suiteKey || '-'}>{suiteKey || '-'}</strong>
                    </div>
                    <div className="functional-suite-context-chip">
                      <span>迭代</span>
                      <strong title={sprintQuery.data?.name || sprintId || '-'}>{sprintQuery.data?.name || sprintId || '-'}</strong>
                    </div>
                    <div className="functional-suite-context-chip functional-suite-context-chip-wide">
                      <span>需求</span>
                      <strong title={requirementQuery.data?.name || requirementId || '-'}>{requirementQuery.data?.name || requirementId || '-'}</strong>
                    </div>
                    <div className="functional-suite-context-chip">
                      <span>数量</span>
                      <strong>{caseTotal}</strong>
                    </div>
                  </div>
                </div>
              </div>

              <section className="workbench-panel api-case-editor-panel functional-case-editor-panel">
                <div className="api-case-editor-shell">
                  <div className="api-case-editor-main">
                    <div className="api-case-editor-main-scroll">
                      {!selectedCaseId ? (
                        <div className="ui-test-case-empty-editor functional-case-empty-editor">
                          <Empty description="请选择一个功能测试用例，或先新建一个用例">
                            <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                              新建用例
                            </ProjectActionButton>
                          </Empty>
                        </div>
                      ) : (
                        <Form<FunctionTestCaseFormValues>
                          form={form}
                          layout="vertical"
                          requiredMark={false}
                          className="functional-case-editor-form"
                          onValuesChange={(_changedValues, allValues) => {
                            if (isCreatingCase) {
                              setDraftCaseValues(allValues as FunctionTestCaseFormValues)
                            }
                          }}
                          onFinish={(values) => {
                            const completeValues = {
                              ...getCompleteCaseFormValues(),
                              ...values,
                              module: suiteName,
                            }
                            saveCaseMutation.mutate(completeValues)
                          }}
                        >
                          <div className="api-case-editor-sticky-head functional-case-editor-sticky-head">
                            <div className="functional-case-toolbar functional-case-editor-hero">
                              <div className="functional-case-name-block">
                                <div className="functional-case-title-row">
                                  <Text className="functional-case-inline-label">用例名称</Text>
                                  {isCreatingCase ? <Tag color="processing">未保存</Tag> : null}
                                </div>
                                <Form.Item
                                  name="title"
                                  className="functional-case-name-item"
                                  rules={[
                                    { required: true, message: '请输入用例标题' },
                                    { validator: validateUniqueTitle },
                                  ]}
                                >
                                  <Input
                                    className="functional-case-title-input"
                                    placeholder="例如：用户使用正确账号密码登录成功"
                                  />
                                </Form.Item>
                                <div className="functional-case-title-meta">
                                  <Text type="secondary">创建时间：{formatTime(pickCreatedAt(currentCase ?? undefined)) || '-'}</Text>
                                  <Text type="secondary">更新时间：{formatTime(pickUpdatedAt(currentCase ?? undefined)) || '-'}</Text>
                                </div>
                              </div>
                              <div className="functional-case-toolbar-actions">
                                <ProjectActionButton action="write"
                                  type="primary"
                                  className="action-btn-save"
                                  operation="save"
                                  loading={saveCaseMutation.isPending}
                                  disabled={batchDeleteMutation.isPending}
                                  onClick={() => form.submit()}
                                >
                                  保存
                                </ProjectActionButton>
                                {!isCreatingCase && currentCase ? (
                                  <Popconfirm
                                    title="确认删除该功能测试用例？"
                                    onConfirm={() => deleteCaseMutation.mutate(normalizeFunctionTestCaseId(currentCase))}
                                  >
                                    <ProjectActionButton action="write" danger operation="delete" disabled={batchDeleteMutation.isPending} loading={deleteCaseMutation.isPending && deleteCaseMutation.variables === normalizeFunctionTestCaseId(currentCase)}>
                                      删除
                                    </ProjectActionButton>
                                  </Popconfirm>
                                ) : null}
                              </div>
                            </div>
                          </div>

                          <div className="functional-case-editor-body">
                            <div className="functional-case-form-grid functional-case-editor-grid functional-case-meta-panel">
                              <Form.Item name="priority" label={<span className="functional-case-meta-label"><FlagOutlined />优先级</span>}>
                                <Select allowClear options={priorityOptions} placeholder="请选择优先级" />
                              </Form.Item>
                              <Form.Item name="caseType" label={<span className="functional-case-meta-label"><ProfileOutlined />用例类型</span>}>
                                <AutoComplete allowClear options={caseTypeOptions} placeholder="请选择或输入用例类型" />
                              </Form.Item>
                            </div>

                            <FunctionCaseContentEditor />
                          </div>
                        </Form>
                      )}
                    </div>
                  </div>
                </div>
              </section>
            </div>
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
      confirmLoading={importFunctionCasesMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={handleImportFunctionCases}
      rootClassName="api-case-import-modal-root"
      className="api-case-import-modal-shell"
      destroyOnHidden
    >
      <div className="api-case-import-modal">
        <Segmented
          className="api-case-import-mode"
          value={caseImportMode}
          options={[
            { label: '上传 JSON', value: 'upload' },
            { label: '直接输入', value: 'editor' },
          ]}
          onChange={(value) => setCaseImportMode(value as CaseImportMode)}
        />
        {caseImportMode === 'upload' ? (
          <div className="api-case-import-upload">
            <Upload.Dragger
              accept=".json"
              maxCount={1}
              beforeUpload={(file) => {
                if (!isJsonFileName(file.name)) {
                  message.error('仅支持 .json 文件')
                  return Upload.LIST_IGNORE
                }
                setImportJsonFile(file)
                return false
              }}
              onRemove={() => {
                setImportJsonFile(null)
                return true
              }}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 JSON 文件到这里</p>
              <p className="ant-upload-hint">仅支持 .json，导入时会自动绑定到当前功能测试集。</p>
            </Upload.Dragger>
          </div>
        ) : (
          <div className="api-case-import-editor">
            <div className="api-case-import-hint">直接粘贴 JSON 内容，提交时前端会将文本包装成 `.json` 文件上传。</div>
            <TextCodeEditor value={importJsonText} onChange={setImportJsonText} language="json" minHeight={280} />
          </div>
        )}
      </div>
    </ProjectActionModal>

    <ProjectActionModal action="execute"
      mask={{ closable: false }}
      open={zentaoImportModalOpen}
      title="导入到禅道"
      width={560}
      okText="开始导入"
      onCancel={closeZentaoImportModal}
      confirmLoading={importZentaoTestCasesMutation.isPending}
      okButtonProps={{ className: 'action-btn-save' }}
      onOk={handleImportZentaoTestCases}
      destroyOnHidden
    >
      <div className="functional-case-zentao-import-modal">
        <Alert
          showIcon
          type="info"
          title={`已选择 ${selectedImportCaseCount} 条，本次将导入 ${zentaoImportTargetCount} 条用例`}
          description={
            selectedImportCaseCount > 0
              ? '只会导入左侧已勾选的用例。如果导入失败并提示资源绑定相关错误，请先完成项目和迭代的禅道绑定。'
              : '未选择用例时默认导入当前测试集全部用例。如果导入失败并提示资源绑定相关错误，请先完成项目和迭代的禅道绑定。'
          }
        />
        <Form<ZentaoImportFormValues>
          form={zentaoImportForm}
          layout="vertical"
          initialValues={{ productId: 1, moduleId: 0 }}
        >
          <Form.Item
            name="productId"
            label="禅道产品 ID"
            rules={[
              { required: true, message: '请输入禅道产品 ID' },
              { type: 'number', min: 1, message: '产品 ID 必须大于 0' },
            ]}
          >
            <InputNumber min={1} precision={0} placeholder="例如：1" />
          </Form.Item>
          <Form.Item name="moduleId" label="禅道模块 ID">
            <InputNumber min={0} precision={0} placeholder="默认 0" />
          </Form.Item>
        </Form>
      </div>
    </ProjectActionModal>
    </>
  )}</ProjectAccessScope>)
}
