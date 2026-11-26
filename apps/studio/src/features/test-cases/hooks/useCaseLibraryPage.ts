import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form, type InputRef } from 'antd'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { useProjectRequirementOptions } from '@/domain/projects/hooks/useProjectRequirementOptions'
import { useSprintRequirementScope } from '@/domain/projects/hooks/useSprintRequirementScope'
import { useWorkbenchStore } from '@/domain/projects/store/workbench.store'
import {
  buildCaseFormValues,
  createDefaultCaseFormValues,
  type FunctionCaseFormValues,
} from '@/features/test-cases/utils/caseForm'
import {
  ApiError,
  api,
  listItems,
  listTotal,
  type FunctionCaseLibraryItem,
  type FunctionTestCase,
  type FunctionTestSuite,
} from '@/services/api'
import {
  invalidatedFilterParam,
  type CaseInvalidationFilter,
} from '@/shared/utils/caseInvalidation'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import type { CaseImportMode } from '@/shared/utils/caseImport'
import { isJsonFileName } from '@/shared/utils/caseImport'
import { message } from '@/shared/utils/feedback'
import {
  getErrorMessage,
  normalizeFunctionTestCaseId,
  normalizeFunctionTestSuiteId,
  normalizeRequirementId,
  normalizeSprintId,
} from '@/utils/format'

/** 测试集 / 用例列表 30s 内视为新鲜：切回本页时先出缓存，不再每次重挂载都重拉。 */
const LIST_STALE_TIME = 30_000

export type SuiteFormValues = {
  sprintId: string
  requirementId: string
  name: string
  description?: string
}

/** 一次禅道导入的目标：测试集、所属需求、要导入的用例（留空表示该测试集全部用例）。 */
export type ZentaoImportTarget = {
  suiteId: string
  requirementId?: string
  caseIds: string[]
  suiteCaseCount: number
}

/** 弹窗在编辑哪条用例：新建草稿，或编辑某条已有用例。 */
export type FunctionCaseEditorTarget =
  | { mode: 'edit'; item: FunctionCaseLibraryItem }
  | { mode: 'create'; suiteId: string; suiteName: string; nextOrderNo: number }

export function suiteRequirementId(suite: FunctionTestSuite) {
  return suite.requirementId ?? suite.requirement_id ?? ''
}

export function suiteCaseCount(suite: FunctionTestSuite) {
  return suite.caseCount ?? suite.case_count ?? 0
}

function getFunctionCaseErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 3301) return '功能测试用例不存在'
    if (error.code === 3302) return '同一个功能测试集下用例标题不能重复'
  }

  return getErrorMessage(error)
}

export function useCaseLibraryPage() {
  const queryClient = useQueryClient()
  const activeProjectId = useWorkbenchStore((state) => state.activeProjectId)

  const [suiteId, setSuiteId] = useState<string | null>(null)
  const [priority, setPriority] = useState<string | null>(null)
  const [caseType, setCaseType] = useState<string | null>(null)
  const [invalidatedFilter, setInvalidatedFilter] = useState<CaseInvalidationFilter>('all')
  const [keyword, setKeyword] = useState('')
  const [searchResetKey, setSearchResetKey] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
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

  const {
    allRequirements,
    allRequirementsQuery,
    requirementNameMap,
    requirementSprintMap,
    sprintNameMap,
  } = useProjectRequirementOptions({ activeProjectId })

  const {
    currentRequirementSelection,
    requirementFilterOptions,
    requirementsLoading,
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
    defaultRequirementSelection: 'all',
    requirementOptions: allRequirements,
    requirementOptionsLoading: allRequirementsQuery.isLoading,
  })
  const selectedSprintId = resolvedSelectedSprintId
  useEffect(() => { setSuiteId(null); setPage(1); setZentaoImportTarget(null) }, [activeProjectId, selectedSprintId])
  const selectedRequirementId = resolvedSelectedRequirementId

  // 翻页保留选择，业务范围变化则清空，避免把旧测试集的 ID 提交给新范围。
  useEffect(() => {
    setSelectedCaseIds([])
  }, [activeProjectId, selectedSprintId, selectedRequirementId, suiteId, invalidatedFilter])

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
    staleTime: LIST_STALE_TIME,
  })
  const suites = listItems(suitesQuery.data)

  const selectedSuite = useMemo(
    () => suites.find((suite) => normalizeFunctionTestSuiteId(suite) === suiteId) ?? null,
    [suiteId, suites],
  )

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
      invalidatedFilter,
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
        invalidated: invalidatedFilterParam(invalidatedFilter),
        keyword,
        page,
        pageSize,
      }),
    enabled: Boolean(activeProjectId) && !sprintsQuery.isLoading,
    staleTime: LIST_STALE_TIME,
  })
  const cases = listItems(casesQuery.data)
  const total = listTotal(casesQuery.data)
  const hasCaseFilters = Boolean(priority || caseType || invalidatedFilter !== 'all' || keyword)
  const hasSuiteData = suitesQuery.data !== undefined
  const hasCaseData = casesQuery.data !== undefined
  const noSuites = suitesQuery.isSuccess && suites.length === 0
  const searchShortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl+K'

  function clearCaseFilters() {
    setPriority(null)
    setCaseType(null)
    setInvalidatedFilter('all')
    setSearchResetKey((current) => current + 1)
    setKeyword('')
    setPage(1)
  }

  const commitKeyword = useCallback((value: string) => {
    setKeyword(value)
    setPage(1)
  }, [])

  // 搜索框右侧标了 ⌘K，那就得真的能按：Mac 用 ⌘，其他平台用 Ctrl。
  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return
      // 标签页常驻挂载后，隐藏面板里的搜索框不能抢占快捷键。
      if (keywordInputRef.current?.nativeElement?.closest('[hidden]')) return
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

  const suiteDrawerRequirements = useMemo(
    () => suiteDrawerSprintId
      ? allRequirements.filter((requirement) => requirement.sprintId === suiteDrawerSprintId)
      : [],
    [allRequirements, suiteDrawerSprintId],
  )

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

  const batchInvalidateCasesMutation = useMutation({
    mutationFn: (invalidated: boolean) =>
      api.batchInvalidateFunctionTestCases(activeProjectId!, selectedCaseIds, invalidated),
    onSuccess: (result, invalidated) => {
      message.success(
        invalidated
          ? `已标记失效 ${result?.updatedCount ?? 0} 条用例`
          : `已恢复有效 ${result?.updatedCount ?? 0} 条用例`,
      )
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      setSelectedCaseIds([])
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
      message.success(`导入成功：${result.imported} 条用例`)
      queryClient.invalidateQueries({ queryKey: ['caseLibraryCases'] })
      queryClient.invalidateQueries({ queryKey: ['caseLibrarySuites'] })
      closeCaseImportModal()
    },
    onError: (error) => message.error(getFunctionCaseErrorMessage(error)),
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

  const canCreateCase = Boolean(selectedSuite?.suiteId)

  return {
    queryClient,
    activeProjectId,
    sprintFilterOptions,
    selectSprint,
    suiteId,
    setSuiteId,
    priority,
    setPriority,
    caseType,
    setCaseType,
    invalidatedFilter,
    setInvalidatedFilter,
    keyword,
    setKeyword,
    searchResetKey,
    setSearchResetKey,
    page,
    setPage,
    pageSize,
    setPageSize,
    keywordInputRef,
    selectedCaseIds,
    setSelectedCaseIds,
    editorTarget,
    setEditorTarget,
    suiteDrawerOpen,
    setSuiteDrawerOpen,
    editingSuite,
    setEditingSuite,
    suiteDrawerSprintId,
    setSuiteDrawerSprintId,
    suiteForm,
    caseForm,
    caseImportOpen,
    setCaseImportOpen,
    caseImportMode,
    setCaseImportMode,
    importJsonFile,
    setImportJsonFile,
    importJsonText,
    setImportJsonText,
    zentaoImportTarget,
    setZentaoImportTarget,
    allRequirements,
    allRequirementsQuery,
    requirementNameMap,
    requirementSprintMap,
    sprintNameMap,
    currentRequirementSelection,
    requirementFilterOptions,
    requirementsLoading,
    resolvedSelectedRequirementId,
    resolvedSelectedSprintId,
    selectRequirement,
    sprints,
    sprintsQuery,
    selectedSprintId,
    selectedRequirementId,
    displayRequirementFilterOptions,
    suitesQuery,
    suites,
    selectedSuite,
    allCaseCount,
    casesQuery,
    cases,
    total,
    hasCaseFilters,
    hasSuiteData,
    hasCaseData,
    noSuites,
    searchShortcut,
    clearCaseFilters,
    commitKeyword,
    describeSuite,
    suiteDrawerRequirements,
    saveSuiteMutation,
    deleteCaseMutation,
    saveCaseMutation,
    batchDeleteCasesMutation,
    batchInvalidateCasesMutation,
    deleteSuiteMutation,
    importFunctionCasesMutation,
    forgetDeletedCases,
    openCreateSuiteDrawer,
    openEditSuiteDrawer,
    openCreateCase,
    openEditCase,
    closeCaseEditor,
    handleCaseSaved,
    closeCaseImportModal,
    openZentaoImport,
    handleImportFunctionCases,
    canCreateCase,
  } as const
}

export type CaseLibraryPageModel = ReturnType<typeof useCaseLibraryPage>
