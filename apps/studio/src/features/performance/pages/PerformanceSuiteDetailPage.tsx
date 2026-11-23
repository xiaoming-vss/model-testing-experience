import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import '@/shared/styles/surface-tokens.css'
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  DownOutlined,
  HistoryOutlined,
  PlusOutlined,
  SaveOutlined,
  SlidersOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { UploadProps } from 'antd'
import { CaseInvalidatedTag } from '@/shared/components/CaseInvalidatedTag'
import { CaseInvalidationModal } from '@/shared/components/CaseInvalidationModal'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import {
  isCaseInvalidated,
  type CaseInvalidationFilter,
} from '@/shared/utils/caseInvalidation'
import { ProjectAccessScope } from '@/domain/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/domain/projects/hooks/useProjectAccess'
import { EnvironmentDrawer } from '@/domain/projects/components/EnvironmentDrawer'
import { api, listItems } from '@/services/api'
import { downloadStoredFile, uploadStoredFile } from '@/shared/api/files'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { PerfCase, PerfDataFile, PerfSuite, PerfSuiteCase } from '../types'
import { buildDefaultPerfYaml, PERF_METHOD_COLORS } from '../utils/perf'
import { formatPerfLoadSummary } from '../utils/perfLoadModel'
import {
  createPerfStep,
  perfCaseFormErrors,
  readPerfCaseForm,
  updatePerfCaseInYaml,
  variablesBeforeStep,
  type PerfCaseFormValues,
  type PerfStepFormValues,
} from '../utils/perfCaseForm'
import {
  clearPerfCaseDraft,
  getPerfCaseDraft,
  setPerfCaseDraft,
} from '../utils/perfDraftStore'
import { PerfCaseDataSection } from '../components/PerfCaseWorkbench'
import { PerfContractToggle, type PerfContractView } from '../components/PerfContractToggle'
import { PerfLoadModelForm } from '../components/PerfLoadModelForm'
import { PerfStepEditor } from '../components/PerfStepsEditor'
import { StartPerfSuiteRunModal } from '../components/StartPerfSuiteRunModal'

const { Text } = Typography

export function PerformanceSuiteDetailPage() {
  const { suiteId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const suiteQuery = useQuery({
    queryKey: ['perfSuite', suiteId],
    queryFn: () => api.getPerfSuite(suiteId),
    enabled: Boolean(suiteId),
  })
  const suite = suiteQuery.data
  const projectId = suite?.projectId
  const { can } = useProjectAccess(projectId ?? '')
  const canWrite = can('write')
  const [invalidatedFilter, setInvalidatedFilter] = useState<CaseInvalidationFilter>('all')
  const [caseStatusOpen, setCaseStatusOpen] = useState(false)
  const requestedCaseId = searchParams.get('case') ?? ''
  const visibleCases = useMemo(
    () =>
      (suite?.cases ?? []).filter((item) => {
        if (invalidatedFilter === 'valid') return !isCaseInvalidated(item)
        if (invalidatedFilter === 'invalid') return isCaseInvalidated(item)
        return true
      }),
    [invalidatedFilter, suite?.cases],
  )
  const invalidatedCount = useMemo(
    () => (suite?.cases ?? []).filter((item) => isCaseInvalidated(item)).length,
    [suite?.cases],
  )
  const activeCase = visibleCases.find((item) => item.caseId === requestedCaseId) ?? visibleCases[0]
  const activeCaseId = activeCase?.caseId ?? ''
  const requestedStepParam = searchParams.get('step')
  const requestedStepIndex = requestedStepParam !== null && /^\d+$/.test(requestedStepParam)
    ? Number(requestedStepParam)
    : null

  const [yaml, setYaml] = useState('')
  const [caseForm, setCaseForm] = useState<PerfCaseFormValues | null>(null)
  const [dataFiles, setDataFiles] = useState<PerfDataFile[]>([])
  const [hydratedCaseId, setHydratedCaseId] = useState('')
  const [collapsedCaseIds, setCollapsedCaseIds] = useState<Set<string>>(() => new Set())
  const [contractView, setContractView] = useState<PerfContractView>('visual')
  const [runOpen, setRunOpen] = useState(false)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [uploading, setUploading] = useState(false)
  const [createCaseOpen, setCreateCaseOpen] = useState(false)
  const [createCaseForm] = Form.useForm<{ name: string }>()

  const batchInvalidateCasesMutation = useMutation({
    mutationFn: ({ caseIds, invalidated }: { caseIds: string[]; invalidated: boolean }) =>
      api.batchInvalidatePerfCases(projectId!, caseIds, invalidated),
    onSuccess: (result, { invalidated }) => {
      message.success(
        invalidated
          ? `已标记失效 ${result?.updatedCount ?? 0} 条用例`
          : `已恢复有效 ${result?.updatedCount ?? 0} 条用例`,
      )
      queryClient.invalidateQueries({ queryKey: ['perfSuite', suiteId] })
      setCaseStatusOpen(false)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', projectId, 'perf'],
    queryFn: () => api.getApiEnvironments(projectId!, 'perf'),
    enabled: Boolean(projectId),
  })
  const environments = listItems(environmentsQuery.data)
  const selectedEnvironment = environments.find((environment) => normalizeEnvironmentId(environment) === selectedEnvironmentId)
    ?? environments.find((environment) => environment.isDefault)
    ?? environments[0]
  const resolvedEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined
  const environmentOptions = environments.map((environment) => ({
    label: `${environment.name}${environment.isDefault ? '（默认）' : ''}`,
    value: normalizeEnvironmentId(environment),
  }))

  useEffect(() => {
    if (!activeCase || hydratedCaseId === activeCase.caseId) return
    const draft = getPerfCaseDraft(activeCase.caseId)
    const nextYaml = draft?.yaml ?? activeCase.yaml
    setYaml(nextYaml)
    setCaseForm(draft?.form ?? readPerfCaseForm(nextYaml, {
      name: activeCase.name,
    }))
    setDataFiles(draft?.dataFiles ?? activeCase.dataFiles)
    setHydratedCaseId(activeCase.caseId)
  }, [activeCase, hydratedCaseId])

  useEffect(() => {
    if (!caseForm || hydratedCaseId !== activeCaseId || requestedStepIndex === null) return
    if (requestedStepIndex >= 0 && requestedStepIndex < caseForm.steps.length) return
    const next = new URLSearchParams(searchParams)
    next.delete('step')
    setSearchParams(next, { replace: true })
  }, [activeCaseId, caseForm, hydratedCaseId, requestedStepIndex, searchParams, setSearchParams])

  const caseHydrated = Boolean(activeCase && hydratedCaseId === activeCase.caseId)
  const activeForm = caseHydrated ? caseForm : null
  const parsedCaseForms = useMemo(() => {
    const forms = new Map<string, PerfCaseFormValues | null>()
    for (const item of suite?.cases ?? []) {
      forms.set(item.caseId, readPerfCaseForm(item.yaml, {
        name: item.name,
      }))
    }
    return forms
  }, [suite])
  const formForCase = (item: PerfSuiteCase) => item.caseId === activeCaseId && activeForm
    ? activeForm
    : parsedCaseForms.get(item.caseId) ?? null
  const selectedStepIndex = activeForm && requestedStepIndex !== null
    && requestedStepIndex >= 0 && requestedStepIndex < activeForm.steps.length
      ? requestedStepIndex
      : null
  const selectedStep = selectedStepIndex !== null && activeForm
    ? activeForm.steps[selectedStepIndex]
    : null
  const errors = useMemo(() => activeForm ? perfCaseFormErrors(activeForm) : [], [activeForm])
  const dirty = Boolean(activeCase && activeForm && (
    yaml !== activeCase.yaml
    || activeForm.name !== activeCase.name
  ))
  const activeDataFiles = caseHydrated ? dataFiles : []

  function applyForm(next: PerfCaseFormValues) {
    setCaseForm(next)
    setYaml(current => updatePerfCaseInYaml(current, next))
  }

  function snapshotDraft() {
    if (!activeCase || !activeForm) return
    if (dirty) {
      setPerfCaseDraft(activeCase.caseId, { yaml, form: activeForm, dataFiles })
    } else {
      clearPerfCaseDraft(activeCase.caseId)
    }
  }

  function toggleCase(caseId: string) {
    setCollapsedCaseIds(current => {
      const next = new Set(current)
      if (next.has(caseId)) next.delete(caseId)
      else next.add(caseId)
      return next
    })
  }

  function selectCase(caseId: string) {
    if (caseId === activeCaseId) {
      if (searchParams.has('step')) {
        const next = new URLSearchParams(searchParams)
        next.delete('step')
        setSearchParams(next, { replace: true })
      }
      return
    }
    snapshotDraft()
    setHydratedCaseId('')
    const next = new URLSearchParams(searchParams)
    next.set('case', caseId)
    next.delete('step')
    setSearchParams(next, { replace: true })
  }

  function selectStep(caseId: string, stepIndex: number) {
    if (caseId !== activeCaseId) {
      snapshotDraft()
      setHydratedCaseId('')
    }
    const next = new URLSearchParams(searchParams)
    next.set('case', caseId)
    next.set('step', String(stepIndex))
    setSearchParams(next, { replace: true })
  }

  function backToCase() {
    if (!searchParams.has('step')) return
    const next = new URLSearchParams(searchParams)
    next.delete('step')
    setSearchParams(next, { replace: true })
  }

  function addStep() {
    if (!activeForm || !activeCase) return
    const step = createPerfStep({ name: `step-${activeForm.steps.length + 1}` })
    const steps = [...activeForm.steps, step]
    applyForm({ ...activeForm, steps })
    const next = new URLSearchParams(searchParams)
    next.set('case', activeCase.caseId)
    next.set('step', String(steps.length - 1))
    setSearchParams(next, { replace: true })
  }

  function updateSelectedStep(patch: Partial<PerfStepFormValues>) {
    if (!activeForm || selectedStepIndex === null) return
    applyForm({
      ...activeForm,
      steps: activeForm.steps.map((step, index) => index === selectedStepIndex ? { ...step, ...patch } : step),
    })
  }

  function moveSelectedStep(offset: -1 | 1) {
    if (!activeForm || selectedStepIndex === null) return
    const target = selectedStepIndex + offset
    if (target < 0 || target >= activeForm.steps.length) return
    const steps = [...activeForm.steps]
    const [step] = steps.splice(selectedStepIndex, 1)
    steps.splice(target, 0, step)
    applyForm({ ...activeForm, steps })
    const next = new URLSearchParams(searchParams)
    next.set('step', String(target))
    setSearchParams(next, { replace: true })
  }

  function removeSelectedStep() {
    if (!activeForm || selectedStepIndex === null) return
    const steps = activeForm.steps.filter((_, index) => index !== selectedStepIndex)
    applyForm({ ...activeForm, steps })
    const next = new URLSearchParams(searchParams)
    if (steps.length === 0) next.delete('step')
    else next.set('step', String(Math.min(selectedStepIndex, steps.length - 1)))
    setSearchParams(next, { replace: true })
  }

  function applySavedCase(updated: PerfCase) {
    clearPerfCaseDraft(updated.caseId)
    queryClient.setQueryData<PerfSuite>(['perfSuite', suiteId], current => current ? {
      ...current,
      cases: current.cases.map((item) => item.caseId === updated.caseId ? {
        ...item,
        name: updated.name,
        yaml: updated.yaml,
        version: updated.version,
        dataFiles: updated.dataFiles,
        updatedAt: updated.updatedAt,
      } : item),
    } : current)
    queryClient.invalidateQueries({ queryKey: ['perfSuites', updated.projectId] })
    setYaml(updated.yaml)
    setDataFiles(updated.dataFiles)
  }

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!activeCase || !activeForm) throw new Error('用例表单尚未就绪')
      return api.updatePerfCase(activeCase.caseId, {
        name: activeForm.name.trim(),
        yaml,
      })
    },
    onSuccess: (updated) => {
      applySavedCase(updated)
      message.success('性能用例已保存')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const createCaseMutation = useMutation({
    mutationFn: (values: { name: string }) => {
      if (!projectId) throw new Error('项目尚未就绪')
      const name = values.name.trim()
      return api.createPerfCase(projectId, {
        name,
        yaml: buildDefaultPerfYaml(name),
        suiteId,
      })
    },
    onSuccess: async (created) => {
      setCreateCaseOpen(false)
      createCaseForm.resetFields()
      await queryClient.invalidateQueries({ queryKey: ['perfSuite', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['perfSuites', projectId] })
      setHydratedCaseId('')
      const next = new URLSearchParams(searchParams)
      next.set('case', created.caseId)
      next.delete('step')
      setSearchParams(next, { replace: true })
      message.success('性能用例已创建')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deletePerfCase(caseId),
    onSuccess: async (_result, caseId) => {
      clearPerfCaseDraft(caseId)
      setCollapsedCaseIds(current => {
        const next = new Set(current)
        next.delete(caseId)
        return next
      })
      queryClient.setQueryData<PerfSuite>(['perfSuite', suiteId], current => current ? {
        ...current,
        cases: current.cases.filter(item => item.caseId !== caseId),
      } : current)
      if (caseId === activeCaseId) {
        setHydratedCaseId('')
        const next = new URLSearchParams(searchParams)
        next.delete('case')
        next.delete('step')
        setSearchParams(next, { replace: true })
      }
      await queryClient.invalidateQueries({ queryKey: ['perfSuite', suiteId] })
      queryClient.invalidateQueries({ queryKey: ['perfSuites', projectId] })
      queryClient.invalidateQueries({ queryKey: ['perfSuiteRuns'] })
      queryClient.invalidateQueries({ queryKey: ['perfSuiteRun'] })
      message.success('性能用例已删除')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const removeDataFileMutation = useMutation({
    mutationFn: (fileId: string) => {
      if (!activeCase) throw new Error('用例尚未就绪')
      return api.updatePerfCase(activeCase.caseId, {
        yaml,
        dataFileIds: dataFiles.filter((item) => item.fileId !== fileId).map((item) => item.fileId),
      })
    },
    onSuccess: (updated) => {
      applySavedCase(updated)
      message.success('数据文件已移除')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function uploadDataFile(file: File) {
    if (!projectId || !activeCase) return
    if (!/\.(csv|json)$/i.test(file.name)) {
      message.warning('数据文件仅支持 CSV / JSON')
      return
    }
    setUploading(true)
    try {
      const fileId = await uploadStoredFile(projectId, file, 'perf_case_data')
      const updated = await api.updatePerfCase(activeCase.caseId, {
        yaml,
        dataFileIds: [...dataFiles.map((item) => item.fileId), fileId],
      })
      applySavedCase(updated)
      message.success('数据文件已上传并关联')
    } catch (error) {
      message.error(getErrorMessage(error))
    } finally {
      setUploading(false)
    }
  }

  const uploadProps: UploadProps = {
    accept: '.csv,.json',
    showUploadList: false,
    multiple: false,
    disabled: uploading || !canWrite || !caseHydrated,
    beforeUpload: (file) => {
      void uploadDataFile(file)
      return false
    },
  }

  async function downloadFile(file: PerfDataFile) {
    try {
      const { blob, filename } = await downloadStoredFile(file.fileId)
      saveBlob(blob, filename || file.filename)
    } catch (error) {
      message.error(getErrorMessage(error))
    }
  }

  const runBlockedReason = !suite
    ? '测试集加载中'
    : suite.cases.length === 0
      ? '测试集没有用例'
      : !suite.cases.some((item) => !isCaseInvalidated(item))
        ? '测试集没有有效用例'
        : !resolvedEnvironmentId
          ? '请先选择性能环境'
          : ''
  const formErrorsAlert = errors.length > 0 ? <Alert
    type="error"
    showIcon
    title={`还有 ${errors.length} 个问题`}
    description={<ul className="m-0 grid gap-0.5 pl-4 text-xs">
      {errors.slice(0, 6).map((error, index) => <li key={`${index}-${error}`}>{error}</li>)}
      {errors.length > 6 ? <li>其余 {errors.length - 6} 个问题请继续检查表单。</li> : null}
    </ul>}
  /> : null

  return <ProjectAccessScope projectId={projectId ?? ''}>
    {suiteQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(suiteQuery.error)} /> : null}
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="tp-board flex min-h-0 flex-1 flex-col">
          <div className="tp-list-toolbar lg:flex-nowrap">
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能测试" className="shrink-0" onClick={() => navigate('/testing?tab=perf')} />
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <h1 className="tp-list-title max-w-[280px] shrink-0 truncate" title={suite?.name ?? '性能测试集'}>
                  {suite?.name ?? '性能测试集'}
                </h1>
                {suite ? <Tag className="m-0 shrink-0">{suite.cases.length} 个用例{invalidatedCount > 0 ? ` · ${invalidatedCount} 已失效` : ''}</Tag> : null}
                <span
                  className="min-w-0 truncate text-xs text-app-surface-text-muted"
                  title={suite ? `${suite.description || '暂无测试集描述'} · 最近更新 ${formatTime(suite.updatedAt)}` : undefined}
                >
                  {suite?.description || '暂无测试集描述'} · 最近更新 {formatTime(suite?.updatedAt)}
                </span>
              </div>
            </div>
            <div className="flex shrink-0 flex-nowrap items-center gap-2">
              <Select
                className="min-w-[140px] max-w-[200px]"
                size="small"
                value={resolvedEnvironmentId}
                options={environmentOptions}
                loading={environmentsQuery.isLoading}
                placeholder="选择性能环境"
                popupMatchSelectWidth={false}
                disabled={!projectId || environments.length === 0}
                onChange={setSelectedEnvironmentId}
              />
              <Button
                size="small"
                icon={<SlidersOutlined />}
                title="环境"
                aria-label="环境"
                onClick={() => setEnvironmentDrawerOpen(true)}
              >
                环境
              </Button>
              <Space size={8} className="shrink-0">
                <Button icon={<HistoryOutlined />} onClick={() => navigate(`/performance/runs?suiteId=${suiteId}`)}>
                  运行记录
                </Button>
                <Tooltip title={runBlockedReason}>
                  <ProjectActionButton
                    action="execute"
                    projectId={projectId}
                    type="primary"
                    operation="run"
                    disabled={Boolean(runBlockedReason)}
                    onClick={() => setRunOpen(true)}
                  >
                    运行测试集
                  </ProjectActionButton>
                </Tooltip>
              </Space>
            </div>
          </div>

          {suiteQuery.isPending ? <div className="grid min-h-[220px] flex-1 place-items-center"><Empty description="性能测试集加载中..." /></div> : suite ? <>
            <div className="grid min-h-0 flex-1 grid-cols-1 items-stretch gap-3 xl:grid-cols-[304px_minmax(0,1fr)]">
              <Card
                size="small"
                className="flex h-full min-h-0 flex-col"
                styles={{ body: { display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 } }}
                title={<span className="inline-flex items-center gap-2"><AppstoreOutlined />用例与接口</span>}
                extra={<Space size={4}>
                  <Tooltip title="管理用例状态"><Button type="text" size="small" disabled={!canWrite || !projectId} onClick={() => setCaseStatusOpen(true)}>用例状态</Button></Tooltip>
                  <Tooltip title="新增用例"><Button type="text" size="small" icon={<PlusOutlined />} aria-label="新增用例" disabled={!canWrite} onClick={() => setCreateCaseOpen(true)} /></Tooltip>
                </Space>}
              >
                <div className="min-h-0 flex-1 overflow-auto pr-1">
                <div className="mb-2 flex flex-wrap items-center gap-2 px-1 text-[12px] text-app-surface-text-muted">
                  <span>状态:</span>
                  {([
                    ['all', '全部'],
                    ['valid', '有效'],
                    ['invalid', '已失效'],
                  ] as const).map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={`tp-chip${invalidatedFilter === value ? ' active' : ''}`}
                      aria-pressed={invalidatedFilter === value}
                      onClick={() => setInvalidatedFilter(value)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <div className="grid gap-2">
                  {visibleCases.map((item) => {
                    const index = suite.cases.findIndex((entry) => entry.caseId === item.caseId)
                    const form = formForCase(item)
                    const steps = form?.steps ?? []
                    const collapsed = collapsedCaseIds.has(item.caseId)
                    const selected = item.caseId === activeCaseId
                    const context = selected && selectedStepIndex !== null
                    return <div key={item.caseId} className="min-w-0">
                      <div className={`flex min-w-0 items-center gap-1 rounded-lg border px-1 py-1 transition-colors ${
                        selected
                          ? context
                            ? 'border-transparent'
                            : 'border-app-accent-border bg-app-accent-surface'
                          : 'border-transparent hover:bg-app-surface-hover'
                      }`}>
                        <button
                          type="button"
                          className="grid h-6 w-5 shrink-0 place-items-center rounded border-0 bg-transparent p-0 text-app-surface-text-muted hover:bg-app-surface-hover"
                          aria-label={`${collapsed ? '展开' : '收起'} ${item.name}`}
                          onClick={() => toggleCase(item.caseId)}
                        >
                          <DownOutlined className={`text-[10px] transition-transform ${collapsed ? '-rotate-90' : ''}`} />
                        </button>
                        <button
                          type="button"
                          className="flex min-w-0 flex-1 items-center gap-2 rounded-md border-0 bg-transparent px-1 py-1 text-left"
                          onClick={() => selectCase(item.caseId)}
                        >
                          <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-app-surface-border bg-app-surface text-[11px] font-semibold text-app-surface-text">{index + 1}</span>
                          <span className="min-w-0 flex-1">
                            <span className={`block truncate text-xs font-semibold ${selected ? 'text-app-accent' : 'text-app-surface-text'}`}>{item.name}</span>
                            <span className="mt-0.5 block truncate text-[11px] text-app-surface-text-muted">{form ? formatPerfLoadSummary(form.load) : '未配置负载'} · {steps.length} 个接口</span>
                          </span>
                          <CaseInvalidatedTag invalidatedAt={item.invalidatedAt} className="flex-none" />
                          <span className="inline-flex min-w-[18px] items-center justify-center rounded-full bg-app-surface-hover px-1.5 text-[10px] text-app-surface-text-muted">{steps.length}</span>
                        </button>
                        {selected ? <Popconfirm
                          title="确认删除该用例？"
                          description="用例及其性能运行记录会一并删除，且无法恢复。"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                          disabled={!canWrite}
                          onConfirm={() => deleteCaseMutation.mutate(item.caseId)}
                        >
                          <Tooltip title="删除用例">
                            <ProjectActionButton
                              action="write"
                              projectId={projectId}
                              title="删除用例"
                              type="text"
                              shape="circle"
                              size="small"
                              className="action-btn-delete shrink-0"
                              operation="delete"
                              iconOnly
                              danger
                              aria-label={`删除用例 ${item.name}`}
                              loading={deleteCaseMutation.isPending && deleteCaseMutation.variables === item.caseId}
                            />
                          </Tooltip>
                        </Popconfirm> : null}
                      </div>
                      {collapsed ? null : <div className="ml-4 mt-1 grid min-w-0 gap-0.5 border-l border-app-surface-border pl-2">
                        {steps.length === 0 ? <div className="px-2 py-1.5 text-[11px] text-app-surface-text-muted">还没有步骤</div> : steps.map((step, stepIndex) => {
                          const activeStep = selected && selectedStepIndex === stepIndex
                          return <button
                            key={`${item.caseId}-${stepIndex}`}
                            type="button"
                            disabled={contractView === 'yaml'}
                            onClick={() => selectStep(item.caseId, stepIndex)}
                            className={`flex w-full min-w-0 items-center gap-2 rounded-md border px-2 py-1.5 text-left transition-colors disabled:cursor-default disabled:opacity-60 ${
                              activeStep
                                ? 'border-app-accent-border bg-app-accent-surface'
                                : 'border-transparent bg-transparent hover:bg-app-surface-hover disabled:hover:bg-transparent'
                            }`}
                          >
                            <Tag color={PERF_METHOD_COLORS[step.method]} className="m-0 shrink-0">{step.method}</Tag>
                            <span className="min-w-0 flex-1">
                              <span className={`block truncate text-xs ${activeStep ? 'font-semibold text-app-accent' : 'text-app-surface-text'}`}>{step.name || '未命名接口'}</span>
                              <span className="block truncate font-mono text-[10px] text-app-surface-text-muted">{step.path || '/'}</span>
                            </span>
                          </button>
                        })}
                        {selected ? <button
                          type="button"
                          disabled={!canWrite || contractView === 'yaml'}
                          onClick={addStep}
                          className="mt-0.5 inline-flex items-center gap-1 rounded-md border-0 bg-transparent px-2 py-1 text-left text-[11px] text-app-surface-text-muted transition-colors hover:bg-app-surface-hover hover:text-app-accent disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <PlusOutlined className="text-[10px]" /> 添加步骤
                        </button> : null}
                      </div>}
                    </div>
                  })}
                  {visibleCases.length === 0 ? <div className="rounded-lg border border-dashed border-app-surface-border px-3 py-5 text-center text-xs text-app-surface-text-muted">{suite.cases.length === 0 ? '还没有用例。' : '没有匹配的用例。'}</div> : null}
                </div>
                </div>
                <ProjectActionButton
                  action="write"
                  projectId={projectId}
                  className="mt-3 w-full"
                  size="small"
                  operation="create"
                  onClick={() => setCreateCaseOpen(true)}
                >
                  添加用例
                </ProjectActionButton>
              </Card>

              <div className="flex min-h-0 min-w-0 flex-col">
                {!activeCase ? <Card size="small">
                  <Empty
                    image={<AppstoreOutlined />}
                    description={<Space orientation="vertical" size={4}>
                      <Text strong>当前测试集还没有性能用例</Text>
                      <Text type="secondary">新增一条用例后，为它选择一个负载模型，再添加要串联执行的 API 步骤。</Text>
                    </Space>}
                  >
                    <ProjectActionButton action="write" projectId={projectId} type="primary" operation="create" onClick={() => setCreateCaseOpen(true)}>
                      新增用例
                    </ProjectActionButton>
                  </Empty>
                </Card> : !caseHydrated ? <Card size="small"><Empty description="用例加载中..." /></Card> : contractView === 'yaml' ? <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--app-panel-radius)] border border-app-surface-border bg-app-surface">
                  <div className="flex flex-none flex-wrap items-center justify-between gap-3 border-b border-[var(--app-surface-divider)] px-4 py-3">
                    <span className="inline-flex min-w-0 items-center gap-2 text-xs">
                      <span className="font-semibold text-app-surface-text">运行契约</span>
                      <span className="truncate text-app-surface-text-muted">{activeCase.name} · 只读，用于排查与 Worker 契约对照</span>
                    </span>
                    <PerfContractToggle value={contractView} onChange={setContractView} />
                  </div>
                  <div className="min-h-0 flex-1 p-4 [&_.json-editor-shell]:h-full [&_.json-editor-shell]:rounded-none [&_.json-editor-shell]:border-0 [&_.json-editor-shell]:bg-transparent [&_.json-editor-shell]:focus-within:shadow-none [&_.json-editor-wrap]:h-full">
                    <TextCodeEditor value={yaml} readOnly language="yaml" height="100%" ariaLabel="内部运行契约" />
                  </div>
                </div> : activeForm && selectedStep && selectedStepIndex !== null ? <>
                  <PerfStepEditor
                    step={selectedStep}
                    stepIndex={selectedStepIndex}
                    stepCount={activeForm.steps.length}
                    variables={variablesBeforeStep(activeForm.steps, selectedStepIndex)}
                    projectId={projectId}
                    environmentName={selectedEnvironment?.name}
                    environmentBaseUrl={selectedEnvironment?.baseUrl}
                    canWrite={canWrite}
                    dirty={dirty}
                    saving={saveMutation.isPending}
                    errors={errors}
                    errorsAlert={formErrorsAlert}
                    onBack={backToCase}
                    onMove={moveSelectedStep}
                    onDelete={removeSelectedStep}
                    onCancel={() => {
                      clearPerfCaseDraft(activeCase.caseId)
                      setHydratedCaseId('')
                    }}
                    onSave={() => saveMutation.mutate()}
                    onChange={updateSelectedStep}
                  />
                </> : activeForm ? <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[var(--app-panel-radius)] border border-app-surface-border bg-app-surface">
                  <div className="flex flex-none flex-wrap items-center justify-between gap-3 border-b border-[var(--app-surface-divider)] px-4 py-3">
                      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
                        <label className="flex min-w-0 flex-1 items-center gap-2 text-xs text-app-surface-text-muted">
                          <span className="shrink-0 whitespace-nowrap">用例名称<span className="text-app-request-error-text"> *</span></span>
                          <Input
                            className="min-w-[240px] flex-1"
                            aria-label="用例名称"
                            value={activeForm.name}
                            status={activeForm.name.trim() ? undefined : 'error'}
                            disabled={!canWrite}
                            onChange={(event) => applyForm({ ...activeForm, name: event.target.value })}
                          />
                        </label>
                        {dirty ? <Tag color="warning" className="m-0">有未保存修改</Tag> : null}
                      </div>
                      <Space size={6} wrap>
                        <PerfContractToggle value={contractView} onChange={setContractView} />
                        <Button
                          size="small"
                          onClick={() => {
                            clearPerfCaseDraft(activeCase.caseId)
                            setHydratedCaseId('')
                          }}
                          disabled={!dirty}
                        >
                          取消
                        </Button>
                        <ProjectActionButton
                          action="write"
                          projectId={projectId}
                          size="small"
                          type="primary"
                          operation="save"
                          icon={<SaveOutlined />}
                          disabled={!dirty || errors.length > 0 || saveMutation.isPending}
                          loading={saveMutation.isPending}
                          onClick={() => saveMutation.mutate()}
                        >
                          保存用例
                        </ProjectActionButton>
                      </Space>
                    </div>
                  {formErrorsAlert ? <div className="flex-none border-b border-[var(--app-surface-divider)] px-4 py-3">{formErrorsAlert}</div> : null}
                  <div className="min-h-0 flex-1 overflow-auto">
                    <PerfLoadModelForm
                      value={activeForm.load}
                      stepCount={activeForm.steps.length}
                      disabled={!canWrite}
                      onChange={load => applyForm({ ...activeForm, load })}
                    />
                    <div className="border-t border-[var(--app-surface-divider)]" />
                    <PerfCaseDataSection
                      value={activeForm}
                      dataFiles={activeDataFiles}
                      disabled={!canWrite}
                      uploading={uploading}
                      uploadProps={uploadProps}
                      removingFileId={removeDataFileMutation.isPending ? removeDataFileMutation.variables : undefined}
                      onChange={applyForm}
                      onDownload={file => void downloadFile(file)}
                      onRemoveFile={file => removeDataFileMutation.mutate(file.fileId)}
                    />
                  </div>
                </div> : <Card size="small" title="无法进入表单编辑">
                  <Alert
                    showIcon
                    type="error"
                    title="当前性能用例 YAML 无法解析"
                    description="表单无法读取 steps / load / data。请切换到 YAML 查看运行契约。"
                    className="mb-3"
                  />
                  <PerfContractToggle value={contractView} onChange={setContractView} />
                </Card>}
              </div>

            </div>
          </> : null}
        </section>
      </div>

      <Modal
        title="新增性能用例"
        open={createCaseOpen}
        onCancel={() => { setCreateCaseOpen(false); createCaseForm.resetFields() }}
        destroyOnHidden
        width={520}
        footer={<Space className="flex justify-end">
          <Button onClick={() => { setCreateCaseOpen(false); createCaseForm.resetFields() }}>取消</Button>
          <Button type="primary" loading={createCaseMutation.isPending} onClick={() => createCaseForm.submit()}>创建并编辑</Button>
        </Space>}
      >
        <Alert
          type="info"
          showIcon
          title="新用例会加入当前测试集的执行顺序末尾"
          description="创建后可在工作台直接编辑负载模型、API 步骤和数据文件。"
          className="mb-3"
        />
        <Form form={createCaseForm} layout="vertical" onFinish={(values) => createCaseMutation.mutate(values)}>
          <Form.Item label="用例名称" name="name" rules={[{ required: true, whitespace: true, message: '请填写用例名称' }]}>
            <Input maxLength={120} placeholder="例如：登录后查询订单" />
          </Form.Item>
        </Form>
      </Modal>

      <CaseInvalidationModal
        open={caseStatusOpen}
        scopeLabel={`${suite?.name ?? '当前性能测试集'} · ${suite?.cases.length ?? 0} 条用例`}
        cases={(suite?.cases ?? []).map((item) => ({
          id: item.caseId,
          name: item.name,
          invalidatedAt: item.invalidatedAt,
        }))}
        canWrite={canWrite && Boolean(projectId)}
        pending={batchInvalidateCasesMutation.isPending}
        onClose={() => setCaseStatusOpen(false)}
        onSubmit={(caseIds, invalidated) =>
          batchInvalidateCasesMutation.mutate({ caseIds, invalidated })
        }
      />
      <StartPerfSuiteRunModal
        open={runOpen}
        projectId={projectId}
        suite={suite ?? null}
        defaultEnvironmentId={resolvedEnvironmentId}
        onClose={() => setRunOpen(false)}
        onStarted={(run) => {
          setRunOpen(false)
          navigate(`/performance/runs/${run.suiteRunId}`)
        }}
        onManageEnvironments={() => { setRunOpen(false); setEnvironmentDrawerOpen(true) }}
        onManageMonitoring={() => { setRunOpen(false); navigate('/base-services?tab=monitoring') }}
      />
      <EnvironmentDrawer
        open={environmentDrawerOpen}
        projectId={projectId}
        kind="perf"
        currentEnvironmentId={resolvedEnvironmentId}
        onClose={() => setEnvironmentDrawerOpen(false)}
        onSelectEnvironment={(environmentId) => setSelectedEnvironmentId(environmentId ?? '')}
      />
    </div>
  </ProjectAccessScope>
}
