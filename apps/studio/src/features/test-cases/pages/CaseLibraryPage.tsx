import { footerRange } from '@/shared/utils/pagination'
import {
  AppstoreOutlined,
  EditOutlined,
  FolderOpenOutlined,
  FolderOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import type { InputRef, TableProps } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useActiveSprint } from '@/features/projects/hooks/useActiveSprint'
import { useProjectRequirements } from '@/features/projects/hooks/useProjectRequirements'
import { useSprintRequirementScope } from '@/features/projects/hooks/useSprintRequirementScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { usePersonalConnectionChoice } from '@/features/base-services/components/usePersonalConnectionChoice'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { FunctionCaseEditor } from '@/features/test-cases/components/FunctionCaseEditor'
import {
  buildCaseFormValues,
  createDefaultCaseFormValues,
  type FunctionCaseFormValues,
} from '@/features/test-cases/utils/caseForm'
import { CASE_TYPE_PRESETS, caseTypeTone } from '@/features/test-cases/utils/caseTone'
import { priorityTone } from '@/shared/utils/priorityTone'
import {
  ApiError,
  api,
  listItems,
  listTotal,
  type FunctionCaseLibraryItem,
  type FunctionTestCase,
  type FunctionTestSuite,
} from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import {
  formatTime,
  getErrorMessage,
  normalizeFunctionTestCaseId,
  normalizeFunctionTestSuiteId,
  normalizeRequirementId,
  normalizeSprintId,
  pickUpdatedAt,
} from '@/utils/format'
import '@/shared/styles/surface-tokens.css'
import '@/features/test-cases/styles/index.css'
import '@/features/test-cases/styles/case-library-v2.css'
import '@/features/test-cases/styles/case-editor-v2.css'

const { Text } = Typography

const PAGE_SIZE_OPTIONS = ['10', '20', '30', '50']

/** 快速过滤条上的优先级档位，顺序即展示顺序（P0 在最前）。 */
const PRIORITY_QUICK_FILTERS = ['P0', 'P1', 'P2', 'P3']

const CASE_TYPE_FILTER_OPTIONS = [
  { label: '全部类型', value: 'all' },
  ...CASE_TYPE_PRESETS.map((value) => ({ label: value, value })),
]

type SuiteFormValues = {
  sprintId: string
  requirementId: string
  name: string
  description?: string
}

type CaseImportMode = 'upload' | 'editor'

type ZentaoImportFormValues = {
  productId: number
  moduleId?: number
}

/** 一次禅道导入的目标：测试集、所属需求、要导入的用例（留空表示该测试集全部用例）。 */
type ZentaoImportTarget = {
  suiteId: string
  requirementId?: string
  caseIds: string[]
  suiteCaseCount: number
}

/** 弹窗在编辑哪条用例：新建草稿，或编辑某条已有用例。 */
type FunctionCaseEditorTarget =
  | { mode: 'edit'; item: FunctionCaseLibraryItem }
  | { mode: 'create'; suiteId: string; suiteName: string; nextOrderNo: number }

function suiteRequirementId(suite: FunctionTestSuite) {
  return suite.requirementId ?? suite.requirement_id ?? ''
}

function suiteCaseCount(suite: FunctionTestSuite) {
  return suite.caseCount ?? suite.case_count ?? 0
}

function isJsonFileName(fileName: string) {
  return /\.json$/i.test(fileName.trim())
}

function getFunctionCaseErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 3301) return '功能测试用例不存在'
    if (error.code === 3302) return '同一个功能测试集下用例标题不能重复'
  }

  return getErrorMessage(error)
}

/**
 * 用例库：左栏测试集（首项「全部用例」），右栏用例列表。
 * 点某一行在抽屉里查看用例，编辑、新建、导入也都在本页完成。
 */
export function CaseLibraryPage() {
  const queryClient = useQueryClient()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)
  const { activeSprintId: globalSprintId, selectSprint: selectGlobalSprint } = useActiveSprint()
  const personalZentao = usePersonalConnectionChoice('zentao')

  const [suiteId, setSuiteId] = useState<string | null>(null)
  const [priority, setPriority] = useState<string | null>(null)
  const [caseType, setCaseType] = useState<string | null>(null)
  const [suiteFilter, setSuiteFilter] = useState('')
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const keywordInputRef = useRef<InputRef>(null)
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([])
  const [editorTarget, setEditorTarget] = useState<FunctionCaseEditorTarget | null>(null)
  const [suiteDrawerOpen, setSuiteDrawerOpen] = useState(false)
  const [editingSuite, setEditingSuite] = useState<FunctionTestSuite | null>(null)
  const [suiteDrawerSprintId, setSuiteDrawerSprintId] = useState<string | undefined>(undefined)
  const [suiteForm] = Form.useForm<SuiteFormValues>()
  const [caseForm] = Form.useForm<FunctionCaseFormValues>()
  const [caseImportOpen, setCaseImportOpen] = useState(false)
  const [caseImportMode, setCaseImportMode] = useState<CaseImportMode>('upload')
  const [importJsonFile, setImportJsonFile] = useState<File | null>(null)
  const [importJsonText, setImportJsonText] = useState('')
  const [zentaoImportTarget, setZentaoImportTarget] = useState<ZentaoImportTarget | null>(null)
  const [zentaoImportForm] = Form.useForm<ZentaoImportFormValues>()

  const {
    currentRequirementSelection,
    currentSprintSelection,
    requirementFilterOptions,
    requirementsQuery,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    selectSprint,
    sprintFilterOptions,
    sprints,
    sprintsQuery,
  } = useSprintRequirementScope({
    activeProjectId,
    includeAllRequirementOption: true,
    includeAllSprintOption: true,
    defaultToAllWhenIncluded: true,
    sprintScope: { value: globalSprintId, onChange: selectGlobalSprint },
  })
  const selectedSprintId = resolvedSelectedSprintId
  const selectedRequirementId = resolvedSelectedRequirementId

  const {
    allRequirements,
    allRequirementsQuery,
    requirementNameMap,
    requirementSprintMap,
    sprintNameMap,
  } = useProjectRequirements({
    activeProjectId,
    enabled: !sprintsQuery.isLoading,
    sprints,
  })

  const displayRequirementFilterOptions = useMemo(() => {
    if (selectedSprintId) return requirementFilterOptions
    return [
      { label: '全部需求', value: 'all' },
      ...allRequirements.map((requirement) => ({
        label: requirement.name,
        value: normalizeRequirementId(requirement),
      })),
    ]
  }, [allRequirements, requirementFilterOptions, selectedSprintId])

  const suitesQuery = useQuery({
    queryKey: ['caseLibrarySuites', activeProjectId, selectedSprintId, selectedRequirementId],
    queryFn: () =>
      api.getProjectFunctionTestSuites(activeProjectId!, {
        sprintId: selectedSprintId ?? '',
        requirementId: selectedRequirementId ?? '',
      }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const suites = listItems(suitesQuery.data)

  const selectedSuite = useMemo(
    () => suites.find((suite) => normalizeFunctionTestSuiteId(suite) === suiteId) ?? null,
    [suiteId, suites],
  )

  // 左栏：项目下的测试集平铺一层，不按需求分组。
  const visibleSuites = useMemo(() => {
    const text = suiteFilter.trim().toLowerCase()
    if (!text) return suites
    return suites.filter((suite) => suite.name.toLowerCase().includes(text))
  }, [suiteFilter, suites])

  // 左栏的计数是「这个桶里有多少用例」，不随关键字 / 优先级变化（测试集行用的就是接口给的 caseCount）。
  // 列表那条的 total 是当前筛选下的结果数，选中测试集后会变成该测试集的，不能拿来当「全部用例」。
  const allCaseCount = useMemo(
    () => suites.reduce((sum, suite) => sum + suiteCaseCount(suite), 0),
    [suites],
  )

  const casesQuery = useQuery({
    queryKey: [
      'caseLibraryCases',
      activeProjectId,
      selectedSprintId,
      selectedRequirementId,
      suiteId,
      priority,
      caseType,
      keyword,
      page,
      pageSize,
    ],
    queryFn: () =>
      api.getProjectFunctionTestCases(activeProjectId!, {
        sprintId: selectedSprintId ?? '',
        requirementId: selectedRequirementId ?? '',
        suiteId: suiteId ?? '',
        priority: priority ?? '',
        caseType: caseType ?? '',
        keyword,
        page,
        pageSize,
      }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
  })
  const cases = listItems(casesQuery.data)
  const total = listTotal(casesQuery.data)
  const hasCaseFilters = Boolean(priority || caseType || keyword)

  useEffect(() => {
    const timer = setTimeout(() => {
      setKeyword(keywordInput.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [keywordInput])

  // 搜索框右侧标了 ⌘K，那就得真的能按：Mac 用 ⌘，其他平台用 Ctrl。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      keywordInputRef.current?.focus()
    }

    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  // 弹窗是按需挂载的，等它挂上来再把这条用例的值灌进表单。
  useEffect(() => {
    if (!editorTarget) return
    caseForm.setFieldsValue(
      editorTarget.mode === 'create'
        ? createDefaultCaseFormValues(editorTarget.nextOrderNo)
        : buildCaseFormValues(editorTarget.item),
    )
  }, [caseForm, editorTarget])

  /** 用例所属的迭代 / 需求 / 测试集：新建、保存后重建抽屉数据都要用。 */
  const describeSuite = useCallback(
    (targetSuiteId: string): Partial<FunctionCaseLibraryItem> => {
      const suite = suites.find((entry) => normalizeFunctionTestSuiteId(entry) === targetSuiteId)
      if (!suite) return { suiteId: targetSuiteId }
      const requirementId = suiteRequirementId(suite)
      const sprintId = requirementSprintMap.get(requirementId)
      return {
        suiteId: targetSuiteId,
        suiteName: suite.name,
        requirementId,
        requirementName: requirementNameMap.get(requirementId),
        sprintId,
        sprintName: sprintId ? sprintNameMap.get(sprintId) : undefined,
      }
    },
    [requirementNameMap, requirementSprintMap, sprintNameMap, suites],
  )

  const suiteDrawerRequirementsQuery = useQuery({
    queryKey: ['requirements', 'caseLibrarySuiteDrawer', suiteDrawerSprintId],
    queryFn: () => api.getRequirements(suiteDrawerSprintId!),
    // 编辑态下这两个下拉是禁用的，但仍要取到选项，否则「所属需求」只会显示需求 ID。
    enabled: suiteDrawerOpen && Boolean(suiteDrawerSprintId),
  })

  const saveSuiteMutation = useMutation({
    mutationFn: (values: SuiteFormValues) => {
      const payload = { name: values.name.trim(), description: (values.description ?? '').trim() }
      return editingSuite?.suiteId
        ? api.updateFunctionTestSuite(editingSuite.suiteId, payload)
        : api.createFunctionTestSuite(values.requirementId, payload)
    },
    onSuccess: () => {
      message.success(editingSuite ? '功能测试集已更新' : '功能测试集已创建')
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      setSuiteDrawerOpen(false)
      setEditingSuite(null)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deleteFunctionTestCase(caseId),
    onSuccess: (_data, caseId) => {
      message.success('用例已删除')
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      forgetDeletedCases([caseId])
    },
    onError: (error) => message.error(getFunctionCaseErrorMessage(error)),
  })

  const saveCaseMutation = useMutation({
    mutationFn: (values: FunctionCaseFormValues) => {
      if (editorTarget?.mode === 'create') {
        return api.createFunctionTestCase(editorTarget.suiteId, {
          ...values,
          module: editorTarget.suiteName,
        })
      }
      const caseId = editorTarget ? normalizeFunctionTestCaseId(editorTarget.item) : ''
      if (!caseId) throw new Error('未获取到功能测试用例 ID')
      return api.updateFunctionTestCase(caseId, {
        ...values,
        module: editorTarget?.mode === 'edit' ? editorTarget.item.suiteName : undefined,
      })
    },
    onSuccess: (testCase) => {
      message.success(editorTarget?.mode === 'create' ? '用例已创建' : '用例已更新')
      handleCaseSaved(testCase)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 3302) {
        caseForm.setFields([{ name: 'title', errors: ['同一个功能测试集下用例标题不能重复'] }])
      }
      message.error(getFunctionCaseErrorMessage(error))
    },
  })

  const batchDeleteCasesMutation = useMutation({
    mutationFn: () => api.batchDeleteFunctionTestCases(suiteId!, selectedCaseIds),
    onSuccess: (result) => {
      message.success(`已删除 ${result?.deletedCount ?? 0} 条用例`)
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      forgetDeletedCases(result?.deletedIds ?? selectedCaseIds)
    },
    onError: (error) => message.error(getFunctionCaseErrorMessage(error)),
  })

  const deleteSuiteMutation = useMutation({
    mutationFn: (targetSuiteId: string) => api.deleteFunctionTestSuite(targetSuiteId),
    onSuccess: () => {
      message.success('功能测试集已删除')
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      setSuiteId(null)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const importFunctionCasesMutation = useMutation({
    mutationFn: ({ file, filename }: { file: Blob; filename: string }) =>
      api.importFunctionTestCases(suiteId!, file, filename),
    onSuccess: (result) => {
      const importedCount =
        result.importedCaseCount ?? result.imported_case_count ?? result.importedCount ?? result.imported_count ?? 0
      message.success(`导入成功：${importedCount} 条用例`)
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      closeCaseImportModal()
    },
    onError: (error) => message.error(getFunctionCaseErrorMessage(error)),
  })

  const importZentaoTestCasesMutation = useMutation({
    mutationFn: async (values: ZentaoImportFormValues) => {
      const target = zentaoImportTarget!
      const connectionId = await personalZentao.forZentaoRequirement(
        activeProjectId ?? '',
        target.requirementId ?? '',
      )
      return api.importFunctionTestCasesToZentao(target.suiteId, {
        ...values,
        connectionId,
        caseIds: target.caseIds.length > 0 ? target.caseIds : undefined,
      })
    },
    onSuccess: (result) => {
      const importedCount =
        result.importedCaseCount ?? result.imported_case_count ?? result.items?.length ?? 0
      message.success(`已导入禅道：${importedCount} 条用例`)
      setZentaoImportTarget(null)
      zentaoImportForm.resetFields()
    },
    onError: (error) => {
      const errorText = `${getErrorMessage(error)}`.toLowerCase()
      message.error(
        /绑定|禅道|zentao|binding/.test(errorText) || (error instanceof ApiError && error.code === 3303)
          ? '导入失败：请先完成项目和迭代的禅道绑定'
          : getFunctionCaseErrorMessage(error),
      )
    },
  })

  /** 删掉的用例如果正开在弹窗里，顺手关掉弹窗并从勾选里摘掉。 */
  function forgetDeletedCases(deletedIds: string[]) {
    const deleted = new Set(deletedIds.filter(Boolean))
    if (deleted.size === 0) return

    setSelectedCaseIds((current) => current.filter((id) => !deleted.has(id)))
    setEditorTarget((current) =>
      current?.mode === 'edit' && deleted.has(normalizeFunctionTestCaseId(current.item))
        ? null
        : current,
    )
  }

  function openCreateSuiteDrawer() {
    const fallbackSprintId = selectedSprintId ?? normalizeSprintId(sprints[0]) ?? undefined
    setEditingSuite(null)
    setSuiteDrawerSprintId(fallbackSprintId)
    suiteForm.setFieldsValue({
      sprintId: fallbackSprintId,
      requirementId: undefined,
      name: '',
      description: '',
    })
    setSuiteDrawerOpen(true)
  }

  function openEditSuiteDrawer(suite: FunctionTestSuite) {
    const requirementId = suiteRequirementId(suite)
    const sprintId = requirementSprintMap.get(requirementId)
    setEditingSuite(suite)
    setSuiteDrawerSprintId(sprintId)
    suiteForm.setFieldsValue({
      sprintId: sprintId ?? '',
      requirementId,
      name: suite.name,
      description: suite.description ?? '',
    })
    setSuiteDrawerOpen(true)
  }

  function openCreateCase() {
    if (!selectedSuite?.suiteId) return
    setEditorTarget({
      mode: 'create',
      suiteId: selectedSuite.suiteId,
      suiteName: selectedSuite.name,
      nextOrderNo: suiteCaseCount(selectedSuite) + 1,
    })
  }

  /** 点用例直接进编辑：没有只读态，也没有单独的编辑按钮。 */
  function openEditCase(item: FunctionCaseLibraryItem) {
    setEditorTarget({ mode: 'edit', item })
  }

  function closeCaseEditor() {
    setEditorTarget(null)
  }

  function handleCaseSaved(testCase: FunctionTestCase) {
    queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
    queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
    setEditorTarget((current) => {
      if (!current) return current
      const scope = current.mode === 'create' ? describeSuite(current.suiteId) : current.item
      const caseId = normalizeFunctionTestCaseId(testCase)
      return { mode: 'edit', item: { ...scope, ...testCase, caseId: caseId || undefined } }
    })
  }

  function closeCaseImportModal() {
    setCaseImportOpen(false)
    setCaseImportMode('upload')
    setImportJsonFile(null)
    setImportJsonText('')
  }

  function openZentaoImport(caseIds: string[]) {
    if (!selectedSuite?.suiteId) return
    zentaoImportForm.setFieldsValue({ productId: 1, moduleId: 0 })
    setZentaoImportTarget({
      suiteId: selectedSuite.suiteId,
      requirementId: suiteRequirementId(selectedSuite),
      caseIds,
      suiteCaseCount: suiteCaseCount(selectedSuite),
    })
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

      importFunctionCasesMutation.mutate({ file: importJsonFile, filename: importJsonFile.name })
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

    const generatedFileName = `function-suite-${suiteId}.json`
    importFunctionCasesMutation.mutate({
      file: new File([jsonContent], generatedFileName, { type: 'application/json' }),
      filename: generatedFileName,
    })
  }

  const columns = useMemo(() => {
    const items: TableProps<FunctionCaseLibraryItem>['columns'] = [
      {
        title: '用例标题',
        key: 'title',
        render: (_, item) => {
          const caseId = normalizeFunctionTestCaseId(item)
          return (
            <Space size={8} className="functional-suite-list-name case-library-title-cell">
              {/* 用例编号是 UUID，标题里放全值太长，按运行历史的既有做法只显示前 8 位。 */}
              {caseId ? (
                <span className="case-library-id-chip" title={caseId}>
                  {caseId.slice(0, 8)}
                </span>
              ) : null}
              <Tooltip title={item.title}>
                <Text ellipsis>{item.title}</Text>
              </Tooltip>
            </Space>
          )
        },
      },
    ]
    // 选中某个测试集时不必再显示「所属测试集」，左栏已经回答了这个信息。
    if (!suiteId) {
      items.push({
        title: '所属测试集',
        key: 'suiteName',
        width: 200,
        ellipsis: true,
        render: (_, item) => (
          <Tooltip title={item.suiteName}>
            <Text className="functional-suite-list-scope" ellipsis>
              {item.suiteName || '-'}
            </Text>
          </Tooltip>
        ),
      })
    }
    items.push(
      {
        title: '模块',
        key: 'module',
        width: 130,
        ellipsis: true,
        render: (_, item) => (
          <Text className="case-library-muted-cell" type="secondary">
            {item.module || '-'}
          </Text>
        ),
      },
      {
        title: '优先级',
        key: 'priority',
        width: 90,
        align: 'center',
        render: (_, item) =>
          item.priority ? (
            <span className={`case-library-priority tone-${priorityTone(item.priority)}`}>
              {item.priority}
            </span>
          ) : (
            <Text type="secondary">-</Text>
          ),
      },
      {
        title: '用例类型',
        key: 'caseType',
        width: 120,
        ellipsis: true,
        render: (_, item) =>
          item.caseType ? (
            <span className={`tp-tone-tag tone-${caseTypeTone(item.caseType)}`}>
              {item.caseType}
            </span>
          ) : (
            <Text type="secondary">-</Text>
          ),
      },
      {
        title: '最近更新',
        key: 'updatedAt',
        width: 180,
        render: (_, item) => (
          <Text className="functional-suite-list-time case-library-time-cell" type="secondary">
            {formatTime(pickUpdatedAt(item))}
          </Text>
        ),
      },
      {
        title: '操作',
        key: 'actions',
        width: 90,
        align: 'right',
        render: (_, item) => (
          <Space
            size={8}
            className="functional-suite-list-actions case-library-row-actions"
            onClick={(event) => event.stopPropagation()}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <Tooltip title="编辑用例">
              <ProjectActionButton
                action="write"
                type="text"
                shape="circle"
                className="action-btn-update"
                operation="edit"
                iconOnly
                aria-label="编辑用例"
                disabled={!item.caseId}
                onClick={() => openEditCase(item)}
              />
            </Tooltip>
            <Popconfirm
              title="确认删除该用例？"
              description="删除后不可恢复。"
              okText="确认删除"
              okButtonProps={{ danger: true }}
              onConfirm={() => item.caseId && deleteCaseMutation.mutate(item.caseId)}
            >
              <Tooltip title="删除用例">
                <ProjectActionButton
                  action="write"
                  type="text"
                  shape="circle"
                  danger
                  className="action-btn-delete"
                  operation="delete"
                  iconOnly
                  aria-label="删除用例"
                  disabled={!item.caseId}
                  loading={
                    deleteCaseMutation.isPending && deleteCaseMutation.variables === item.caseId
                  }
                />
              </Tooltip>
            </Popconfirm>
          </Space>
        ),
      },
    )
    return items
  }, [deleteCaseMutation, suiteId])

  // 弹窗头部：用例身份（序号 / UID）与这次在做什么。新建时还没有编号，显示「未保存」。
  const editingCaseId = editorTarget?.mode === 'edit' ? normalizeFunctionTestCaseId(editorTarget.item) : ''
  const editingOrderNo = editorTarget?.mode === 'edit' ? editorTarget.item.orderNo : undefined
  const caseEditorHeader = (
    <div className="case-editor-head">
      <span className="case-editor-head-icon">
        <EditOutlined />
      </span>
      <div className="case-editor-head-copy">
        <div className="case-editor-head-title">
          <span className="case-editor-head-name">
            {editorTarget?.mode === 'create' ? '新建用例' : '编辑用例'}
          </span>
          {editingOrderNo ? (
            <span className="case-editor-head-badge" title="该测试集内的用例序号">
              TC-{String(editingOrderNo).padStart(4, '0')}
            </span>
          ) : null}
          {editingCaseId ? (
            <span className="case-editor-head-uid">UID: {editingCaseId.slice(0, 8)}</span>
          ) : (
            <span className="case-editor-head-badge">未保存</span>
          )}
        </div>
        <p className="case-editor-head-subtitle">
          {editorTarget?.mode === 'create'
            ? '填写用例的执行规范与验证结果'
            : '修改并完善当前测试用例的执行规范及验证结果'}
        </p>
      </div>
    </div>
  )

  // 新建用例、用例导入与测试集操作都按测试集执行，未选中测试集时整组不显示。
  const canCreateCase = Boolean(selectedSuite?.suiteId)
  const zentaoImportCaseCount = zentaoImportTarget
    ? zentaoImportTarget.caseIds.length || zentaoImportTarget.suiteCaseCount
    : 0

  return (
    <div className="workbench-page api-automation-page functional-test-page case-library-page tp-surface">
      {personalZentao.dialog}
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          <div className="panel-header api-panel-header case-library-toolbar">
            <div className="api-filter-group case-library-filters">
              <div className="api-filter-field">
                <span className="api-filter-field-label">迭代</span>
                <Select
                  className="api-filter-select business-filter-select"
                  value={currentSprintSelection === null ? 'all' : selectedSprintId ?? 'all'}
                  options={sprintFilterOptions}
                  loading={sprintsQuery.isLoading}
                  placeholder="请选择迭代"
                  onChange={(value: string) => {
                    selectSprint(value === 'all' ? null : value)
                    if (value === 'all') selectRequirement(null)
                    setSuiteId(null)
                    setPage(1)
                  }}
                />
              </div>
              <div className="api-filter-field">
                <span className="api-filter-field-label">需求</span>
                <Select
                  className="api-filter-select business-filter-select"
                  value={
                    currentRequirementSelection === null ? 'all' : selectedRequirementId ?? 'all'
                  }
                  options={displayRequirementFilterOptions}
                  loading={requirementsQuery.isLoading || allRequirementsQuery.isLoading}
                  placeholder="请选择需求"
                  disabled={!selectedSprintId && allRequirements.length === 0}
                  onChange={(value: string) => {
                    selectRequirement(value === 'all' ? null : value)
                    setSuiteId(null)
                    setPage(1)
                  }}
                />
              </div>
              <div className="api-filter-field">
                <span className="api-filter-field-label">用例类型</span>
                <Select
                  className="api-filter-select business-filter-select"
                  value={caseType ?? 'all'}
                  options={CASE_TYPE_FILTER_OPTIONS}
                  onChange={(value: string) => {
                    setCaseType(value === 'all' ? null : value)
                    setPage(1)
                  }}
                />
              </div>
              <div className="api-filter-field case-library-search-field">
                <Input
                  ref={keywordInputRef}
                  className="api-filter-input case-library-search-input"
                  allowClear
                  prefix={<SearchOutlined />}
                  suffix={<span className="case-library-search-hint">⌘K</span>}
                  placeholder="搜索用例名称 / 模块"
                  value={keywordInput}
                  onChange={(event) => setKeywordInput(event.target.value)}
                />
              </div>
            </div>

            <Space size={8} className="case-library-toolbar-actions">
              {selectedSuite ? (
                <Space size={8} className="case-library-main-actions">
                  <ProjectActionButton
                    action="write"
                    type="primary"
                    className="action-btn-create"
                    operation="create"
                    onClick={openCreateCase}
                  >
                    新建用例
                  </ProjectActionButton>
                  <ProjectActionButton
                    action="execute"
                    className="action-btn-update"
                    operation="upload"
                    onClick={() => setCaseImportOpen(true)}
                  >
                    用例导入
                  </ProjectActionButton>
                  <ProjectActionButton
                    action="execute"
                    className="action-btn-update"
                    operation="upload"
                    disabled={suiteCaseCount(selectedSuite) === 0}
                    onClick={() => openZentaoImport(selectedCaseIds)}
                  >
                    导入禅道
                  </ProjectActionButton>
                </Space>
              ) : null}
              <Tooltip title="刷新用例列表">
                <ProjectActionButton
                  action="read"
                  type="text"
                  shape="circle"
                  className="action-btn-read case-library-refresh"
                  operation="refresh"
                  icon={<ReloadOutlined />}
                  iconOnly
                  aria-label="刷新用例列表"
                  loading={casesQuery.isFetching || suitesQuery.isFetching}
                  onClick={() => {
                    casesQuery.refetch()
                    suitesQuery.refetch()
                  }}
                />
              </Tooltip>
              <Popconfirm
                title={`确认删除选中的 ${selectedCaseIds.length} 条用例？`}
                description="删除后不可恢复。"
                okText="确认删除"
                okButtonProps={{ danger: true }}
                disabled={!suiteId || selectedCaseIds.length === 0}
                onConfirm={() => batchDeleteCasesMutation.mutate()}
              >
                <Tooltip
                  title={
                    suiteId ? undefined : '批量删除按测试集执行，请先在左栏选中一个测试集'
                  }
                >
                  <ProjectActionButton
                    action="write"
                    danger
                    className="action-btn-delete"
                    operation="delete"
                    disabled={!suiteId || selectedCaseIds.length === 0}
                    loading={batchDeleteCasesMutation.isPending}
                  >
                    批量删除{selectedCaseIds.length > 0 ? `（${selectedCaseIds.length}）` : ''}
                  </ProjectActionButton>
                </Tooltip>
              </Popconfirm>
            </Space>
          </div>

          {sprintsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(sprintsQuery.error)} />
          ) : null}
          {allRequirementsQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(allRequirementsQuery.error)} />
          ) : null}
          {suitesQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} />
          ) : null}
          {casesQuery.error ? (
            <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} />
          ) : null}

          {!activeProjectId ? (
            <div className="sprint-card-loading">
              <Empty description="请先选择项目" />
            </div>
          ) : !sprintsQuery.isLoading && sprints.length === 0 ? (
            <div className="sprint-card-loading">
              <Empty description="当前项目下暂无迭代" />
            </div>
          ) : (
            <div className="case-library-layout">
              <aside className="api-case-sidebar case-library-tree">
                <div className="case-library-tree-head">
                  <span className="case-library-tree-title">
                    <FolderOpenOutlined />
                    测试集导航
                  </span>
                </div>
                <div className="api-case-sidebar-toolbar case-library-tree-search">
                  <Input
                    allowClear
                    prefix={<SearchOutlined />}
                    placeholder="搜索测试集"
                    value={suiteFilter}
                    onChange={(event) => setSuiteFilter(event.target.value)}
                  />
                </div>
                <div className="api-case-sidebar-scroll case-library-tree-scroll">
                  <div className="api-case-nav-list case-library-nav-list">
                    <button
                      type="button"
                      className={`api-case-nav-item case-library-nav-item${suiteId ? '' : ' active'
                      }`}
                      aria-current={!suiteId}
                      onClick={() => {
                        setSuiteId(null)
                        setPage(1)
                      }}
                    >
                      <span className="case-library-nav-main">
                        <AppstoreOutlined className="case-library-tree-icon" />
                        <span className="case-library-nav-name">全部用例</span>
                      </span>
                      <span className="case-library-nav-count">{allCaseCount}</span>
                    </button>
                    {suitesQuery.isLoading ? (
                      <div className="sprint-card-loading">
                        <Empty description="测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      </div>
                    ) : visibleSuites.length === 0 ? (
                      <div className="sprint-card-loading">
                        <Empty description="没有匹配的测试集" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                      </div>
                    ) : (
                      visibleSuites.map((suite) => {
                        const id = normalizeFunctionTestSuiteId(suite)
                        const active = Boolean(id) && id === suiteId
                        return (
                          <button
                            key={id ?? suite.name}
                            type="button"
                            className={`api-case-nav-item case-library-nav-item${active ? ' active' : ''
                            }`}
                            aria-current={active}
                            onClick={() => {
                              setSuiteId(id ?? null)
                              setPage(1)
                            }}
                          >
                            <span className="case-library-nav-main">
                              {active ? (
                                <FolderOpenOutlined className="case-library-tree-icon" />
                              ) : (
                                <FolderOutlined className="case-library-tree-icon" />
                              )}
                              <span className="case-library-nav-name">{suite.name}</span>
                            </span>
                            <span className="case-library-nav-count">{suiteCaseCount(suite)}</span>
                          </button>
                        )
                      })
                    )}
                  </div>
                </div>
                {/* 三个动作排一行：新建常驻且带文字，编辑 / 删除要靠选中测试集，收成图标按钮。 */}
                <div className="case-library-sidebar-foot">
                  <Tooltip title="新建测试集">
                    <ProjectActionButton
                      action="write"
                      type="text"
                      className="action-btn-create case-library-foot-create"
                      operation="create"
                      icon={<PlusOutlined />}
                      disabled={!activeProjectId || sprints.length === 0}
                      onClick={openCreateSuiteDrawer}
                    >
                      新建测试集
                    </ProjectActionButton>
                  </Tooltip>
                  <Tooltip title={selectedSuite ? '编辑测试集' : '编辑按测试集执行，请先选中一个测试集'}>
                    <ProjectActionButton
                      action="write"
                      type="text"
                      shape="circle"
                      className="action-btn-update"
                      operation="edit"
                      iconOnly
                      aria-label="编辑测试集"
                      disabled={!selectedSuite}
                      onClick={() => selectedSuite && openEditSuiteDrawer(selectedSuite)}
                    />
                  </Tooltip>
                  <Popconfirm
                    title="确认删除该功能测试集？"
                    description="测试集下若还有用例需先删除用例，删除后不可恢复。"
                    okText="确认删除"
                    okButtonProps={{ danger: true }}
                    disabled={!selectedSuite}
                    onConfirm={() =>
                      selectedSuite?.suiteId && deleteSuiteMutation.mutate(selectedSuite.suiteId)
                    }
                  >
                    <Tooltip title={selectedSuite ? '删除测试集' : '删除按测试集执行，请先选中一个测试集'}>
                      <ProjectActionButton
                        action="write"
                        type="text"
                        shape="circle"
                        className="action-btn-delete"
                        operation="delete"
                        iconOnly
                        aria-label="删除测试集"
                        disabled={!selectedSuite}
                        loading={deleteSuiteMutation.isPending}
                      />
                    </Tooltip>
                  </Popconfirm>
                </div>
              </aside>

              <div className="case-library-main">
                {/* 优先级不进筛选下拉：档位只有四档，摊平成一排比藏在二级菜单里快。 */}
                <div className="tp-quickbar case-library-quickbar">
                  <div className="tp-quick-filters">
                    <span className="tp-quick-label">快速过滤:</span>
                    <button
                      type="button"
                      className={`tp-chip${priority ? '' : ' active'}`}
                      aria-pressed={!priority}
                      onClick={() => {
                        setPriority(null)
                        setPage(1)
                      }}
                    >
                      全部
                      <span className="tp-chip-count">{total}</span>
                    </button>
                    {PRIORITY_QUICK_FILTERS.map((level) => (
                      <button
                        key={level}
                        type="button"
                        className={`tp-chip case-library-chip-priority${priority === level ? ' active' : ''}`}
                        aria-pressed={priority === level}
                        onClick={() => {
                          setPriority(priority === level ? null : level)
                          setPage(1)
                        }}
                      >
                        {level}
                      </button>
                    ))}
                  </div>
                  <div className="tp-selection">
                    已选 <strong>{selectedCaseIds.length}</strong> 项 · 共 <strong>{total}</strong> 条用例
                  </div>
                </div>
                <div className="table-body-scroll sprint-card-scroll case-library-table-scroll">
                  {casesQuery.isLoading ? (
                    <div className="sprint-card-loading">
                      <Empty description="用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    </div>
                  ) : cases.length === 0 ? (
                    <div className="sprint-card-loading">
                      <Empty
                        image={<AppstoreOutlined />}
                        description={
                          <Space orientation="vertical" size={4}>
                            <Text strong>
                              {hasCaseFilters ? '没有符合筛选条件的用例' : '这里还没有功能用例'}
                            </Text>
                            <Text type="secondary">
                              {hasCaseFilters
                                ? '调整或清空筛选条件后再看。'
                                : '在左栏选中测试集后可以直接新建用例，也可以用例导入或 AI 生成后导入。'}
                            </Text>
                          </Space>
                        }
                      >
                        {hasCaseFilters || !canCreateCase ? null : (
                          <ProjectActionButton
                            action="write"
                            type="primary"
                            className="action-btn-create"
                            operation="create"
                            onClick={openCreateCase}
                          >
                            新建用例
                          </ProjectActionButton>
                        )}
                      </Empty>
                    </div>
                  ) : (
                    <Table<FunctionCaseLibraryItem>
                      className="functional-suite-list-table"
                      columns={columns}
                      dataSource={cases}
                      rowKey={(item) => normalizeFunctionTestCaseId(item) ?? item.title}
                      rowSelection={{
                        preserveSelectedRowKeys: true,
                        selectedRowKeys: selectedCaseIds,
                        onChange: (keys) => setSelectedCaseIds(keys.map(String)),
                        getCheckboxProps: (item) => ({
                          disabled: !normalizeFunctionTestCaseId(item),
                          'aria-label': `选择用例：${item.title}`,
                        }),
                      }}
                      pagination={false}
                      onRow={(item) => ({
                        onClick: (event) => {
                          if ((event.target as HTMLElement).closest('.ant-table-selection-column'))
                            return
                          openEditCase(item)
                        },
                      })}
                    />
                  )}
                </div>

                <div className="table-footer case-library-footer">
                  <Text type="secondary">{footerRange(total, page, pageSize)}</Text>
                  <Pagination
                    current={page}
                    pageSize={pageSize}
                    total={total}
                    showSizeChanger
                    pageSizeOptions={PAGE_SIZE_OPTIONS}
                    onChange={(nextPage, nextPageSize) => {
                      setPageSize(nextPageSize)
                      setPage(nextPageSize === pageSize ? nextPage : 1)
                    }}
                  />
                </div>
              </div>
            </div>
          )}
        </section>
      </div>

      {editorTarget ? (
        <Modal
          open
          centered
          width={1040}
          maskClosable={false}
          className="case-library-case-modal tp-surface"
          title={caseEditorHeader}
          onCancel={closeCaseEditor}
          footer={
            <div className="case-editor-footer">
              {/* 删除是危险动作，按设计稿收在底部最左侧，和右侧的确认动作分开。 */}
              {editorTarget.mode === 'edit' ? (
                <Popconfirm
                  title="确认删除该用例？"
                  description="删除后不可恢复。"
                  okText="确认删除"
                  okButtonProps={{ danger: true }}
                  onConfirm={() =>
                    deleteCaseMutation.mutate(normalizeFunctionTestCaseId(editorTarget.item))
                  }
                >
                  <ProjectActionButton
                    action="write"
                    danger
                    type="text"
                    className="action-btn-delete"
                    operation="delete"
                    disabled={saveCaseMutation.isPending}
                    loading={deleteCaseMutation.isPending}
                  >
                    删除用例
                  </ProjectActionButton>
                </Popconfirm>
              ) : null}
              <Space size={8} className="case-editor-footer-main">
                <ProjectActionButton
                  action="write"
                  disabled={saveCaseMutation.isPending}
                  onClick={closeCaseEditor}
                >
                  取消
                </ProjectActionButton>
                <ProjectActionButton
                  action="write"
                  type="primary"
                  className="action-btn-save"
                  operation="save"
                  loading={saveCaseMutation.isPending}
                  onClick={() => caseForm.submit()}
                >
                  保存变更
                </ProjectActionButton>
              </Space>
            </div>
          }
        >
          <FunctionCaseEditor
            form={caseForm}
            isCreate={editorTarget.mode === 'create'}
            item={editorTarget.mode === 'edit' ? editorTarget.item : null}
            onSubmit={(values) =>
              // orderNo 这类字段没有对应的表单项，只能从表单全量取值里补回来。
              saveCaseMutation.mutate({
                ...(caseForm.getFieldsValue(true) as FunctionCaseFormValues),
                ...values,
              })
            }
          />
        </Modal>
      ) : null}

      <Drawer
        title={editingSuite ? '编辑功能测试集' : '新建功能测试集'}
        open={suiteDrawerOpen}
        onClose={() => {
          setSuiteDrawerOpen(false)
          setEditingSuite(null)
        }}
        size={520}
        extra={
          <ProjectActionButton
            action="write"
            type="primary"
            className="action-btn-save"
            onClick={() => suiteForm.submit()}
          >
            {saveSuiteMutation.isPending ? '保存中...' : '保存'}
          </ProjectActionButton>
        }
      >
        <Form
          form={suiteForm}
          layout="vertical"
          requiredMark={false}
          onFinish={(values) => saveSuiteMutation.mutate(values)}
        >
          <Form.Item
            label="所属迭代"
            name="sprintId"
            rules={[{ required: true, message: '请选择迭代' }]}
          >
            <Select
              options={sprints.map((sprint) => ({
                label: sprint.name,
                value: normalizeSprintId(sprint),
              }))}
              placeholder="请选择迭代"
              disabled={Boolean(editingSuite)}
              onChange={(value: string) => {
                setSuiteDrawerSprintId(value)
                suiteForm.setFieldsValue({ requirementId: undefined })
              }}
            />
          </Form.Item>
          <Form.Item
            label="所属需求"
            name="requirementId"
            rules={[{ required: true, message: '请选择需求' }]}
          >
            <Select
              options={listItems(suiteDrawerRequirementsQuery.data).map((requirement) => ({
                label: requirement.name,
                value: normalizeRequirementId(requirement),
              }))}
              loading={suiteDrawerRequirementsQuery.isLoading}
              placeholder="请选择需求"
              disabled={Boolean(editingSuite)}
            />
          </Form.Item>
          <Form.Item
            label="测试集名称"
            name="name"
            rules={[{ required: true, message: '请输入测试集名称' }]}
          >
            <Input placeholder="例如：登录与鉴权" maxLength={100} />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea rows={3} placeholder="例如：登录主流程 / 订单核心链路" maxLength={512} />
          </Form.Item>
        </Form>
      </Drawer>

      <ProjectActionModal
        action="execute"
        mask={{ closable: false }}
        open={caseImportOpen}
        title="用例导入"
        width={860}
        okText="开始导入"
        cancelText="取消"
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
                <p className="ant-upload-hint">
                  仅支持 .json，导入时会自动绑定到左栏选中的测试集。
                </p>
              </Upload.Dragger>
            </div>
          ) : (
            <div className="api-case-import-editor">
              <div className="api-case-import-hint">
                直接粘贴 JSON 内容，提交时前端会将文本包装成 `.json` 文件上传。
              </div>
              <TextCodeEditor
                value={importJsonText}
                onChange={setImportJsonText}
                language="json"
                minHeight={280}
              />
            </div>
          )}
        </div>
      </ProjectActionModal>

      <ProjectActionModal
        action="execute"
        mask={{ closable: false }}
        open={Boolean(zentaoImportTarget)}
        title="导入到禅道"
        width={560}
        okText="开始导入"
        cancelText="取消"
        onCancel={() => {
          if (importZentaoTestCasesMutation.isPending) return
          setZentaoImportTarget(null)
        }}
        confirmLoading={importZentaoTestCasesMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
        onOk={() => zentaoImportForm.submit()}
        destroyOnHidden
      >
        <div className="functional-case-zentao-import-modal">
          <Alert
            showIcon
            type="info"
            title={`本次将导入 ${zentaoImportCaseCount} 条用例`}
            description={
              zentaoImportTarget && zentaoImportTarget.caseIds.length > 0
                ? '只会导入本次选中的用例。如果导入失败并提示资源绑定相关错误，请先完成项目和迭代的禅道绑定。'
                : '默认导入该测试集全部用例。如果导入失败并提示资源绑定相关错误，请先完成项目和迭代的禅道绑定。'
            }
          />
          <Form<ZentaoImportFormValues>
            form={zentaoImportForm}
            layout="vertical"
            initialValues={{ productId: 1, moduleId: 0 }}
            onFinish={(values) => importZentaoTestCasesMutation.mutate(values)}
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
    </div>
  )
}
