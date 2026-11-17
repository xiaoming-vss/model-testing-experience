import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ApiOutlined,
  AppstoreOutlined,
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  CodeOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  HistoryOutlined,
  KeyOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SaveOutlined,
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
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { UploadProps } from 'antd'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { EnvironmentDrawer } from '@/features/projects/components/EnvironmentDrawer'
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
import { PerfLoadModelForm } from '../components/PerfLoadModelForm'
import { PerfStepFields } from '../components/PerfStepsEditor'
import { PerfSuiteDrawer, type PerfSuiteFormValues } from '../components/PerfSuiteDrawer'
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
  const requestedCaseId = searchParams.get('case') ?? ''
  const activeCase = suite?.cases.find((item) => item.caseId === requestedCaseId) ?? suite?.cases[0]
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
  const [internalDataOpen, setInternalDataOpen] = useState(false)
  const [runOpen, setRunOpen] = useState(false)
  const [suiteDrawerOpen, setSuiteDrawerOpen] = useState(false)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [uploading, setUploading] = useState(false)
  const [createCaseOpen, setCreateCaseOpen] = useState(false)
  const [createCaseForm] = Form.useForm<{ name: string }>()

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

  useEffect(() => {
    if (!activeCase || hydratedCaseId === activeCase.caseId) return
    const draft = getPerfCaseDraft(activeCase.caseId)
    const nextYaml = draft?.yaml ?? activeCase.yaml
    setYaml(nextYaml)
    setCaseForm(draft?.form ?? readPerfCaseForm(nextYaml, {
      name: activeCase.name,
      enabled: activeCase.enabled,
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
        enabled: item.enabled,
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
    || activeForm.enabled !== activeCase.enabled
  ))
  const extractVariables = activeForm
    ? Array.from(new Set(activeForm.steps.flatMap(step => step.extract.map(item => item.name.trim()).filter(Boolean))))
    : []
  const variables = useMemo(() => {
    if (!suite) return []
    return suite.cases.flatMap((item) => {
      const form = item.caseId === activeCaseId && activeForm
        ? activeForm
        : parsedCaseForms.get(item.caseId)
      if (!form) return []
      return form.steps.flatMap((step, stepIndex) => step.extract
        .filter((extract) => extract.name.trim())
        .map((extract) => ({
          name: extract.name.trim(),
          caseName: item.name,
          caseId: item.caseId,
          stepIndex,
          stepName: step.name,
        })))
    })
  }, [suite, activeCaseId, activeForm, parsedCaseForms])
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
        enabled: updated.enabled,
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
        enabled: activeForm.enabled,
      })
    },
    onSuccess: (updated) => {
      applySavedCase(updated)
      message.success('性能用例已保存')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const updateSuiteMutation = useMutation({
    mutationFn: (values: PerfSuiteFormValues) => api.updatePerfSuite(suiteId, {
      name: values.name.trim(),
      description: values.description?.trim() ?? '',
      enabled: values.enabled,
    }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['perfSuite', suiteId], updated)
      queryClient.invalidateQueries({ queryKey: ['perfSuites', updated.projectId] })
      setSuiteDrawerOpen(false)
      message.success('测试集信息已更新')
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

  const enabledCases = suite?.cases.filter((item) => item.enabled) ?? []
  const runBlockedReason = !suite?.enabled
    ? '测试集已停用'
    : enabledCases.length === 0
      ? '测试集没有启用的用例'
      : !resolvedEnvironmentId
        ? '请先选择性能环境'
        : ''
  const formErrorsAlert = errors.length > 0 ? <Alert
    type="error"
    showIcon
    className="mt-3"
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
        <section className="workbench-panel workbench-board-panel tp-board">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能测试" onClick={() => navigate('/testing?tab=perf')} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="tp-list-title">{suite?.name ?? '性能测试集'}</h1>
                  {suite ? <Tag color={suite.enabled ? 'success' : 'default'}>{suite.enabled ? '已启用' : '已停用'}</Tag> : null}
                  <Tag color="blue">串行执行</Tag>
                  {suite ? <Tag>{suite.cases.length} 个用例</Tag> : null}
                </div>
                <div className="mt-1 text-xs text-app-surface-text-muted">
                  {suite?.description || '暂无测试集描述'} · 最近更新 {formatTime(suite?.updatedAt)}
                </div>
              </div>
            </div>
            <Space size={8} wrap>
              <Button icon={<HistoryOutlined />} onClick={() => navigate(`/performance/runs?suiteId=${suiteId}`)}>
                运行记录
              </Button>
              <Button icon={<EditOutlined />} disabled={!suite || !canWrite} onClick={() => setSuiteDrawerOpen(true)}>
                编辑信息
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

          {suiteQuery.isPending ? <div className="p-10"><Empty description="性能测试集加载中..." /></div> : suite ? <>
            <div className="grid grid-cols-1 gap-4 p-4 xl:grid-cols-[304px_minmax(0,1fr)_320px]">
              <Card
                size="small"
                className="self-start xl:sticky xl:top-4"
                title={<span className="inline-flex items-center gap-2"><AppstoreOutlined />用例与接口</span>}
                extra={<Tooltip title="新增用例"><Button type="text" size="small" icon={<PlusOutlined />} aria-label="新增用例" disabled={!canWrite} onClick={() => setCreateCaseOpen(true)} /></Tooltip>}
              >
                <div className="grid gap-2">
                  {suite.cases.map((item, index) => {
                    const form = formForCase(item)
                    const steps = form?.steps ?? []
                    const collapsed = collapsedCaseIds.has(item.caseId)
                    const selected = item.caseId === activeCaseId
                    const context = selected && selectedStepIndex !== null
                    return <div key={item.caseId}>
                      <div className={`flex items-center gap-1 rounded-lg border px-1 py-1 transition-colors ${
                        selected
                          ? context
                            ? 'border-transparent'
                            : 'border-app-accent-border bg-app-accent-surface'
                          : 'border-transparent hover:bg-app-surface-hover'
                      } ${item.enabled ? '' : 'opacity-60'}`}>
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
                          <span className="inline-flex min-w-[18px] items-center justify-center rounded-full bg-app-surface-hover px-1.5 text-[10px] text-app-surface-text-muted">{steps.length}</span>
                        </button>
                      </div>
                      {collapsed ? null : <div className="ml-4 mt-1 grid gap-0.5 border-l border-app-surface-border pl-2">
                        {steps.length === 0 ? <div className="px-2 py-1.5 text-[11px] text-app-surface-text-muted">还没有接口</div> : steps.map((step, stepIndex) => {
                          const activeStep = selected && selectedStepIndex === stepIndex
                          return <button
                            key={`${item.caseId}-${stepIndex}`}
                            type="button"
                            onClick={() => selectStep(item.caseId, stepIndex)}
                            className={`flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left transition-colors ${
                              activeStep
                                ? 'border-app-accent-border bg-app-accent-surface'
                                : 'border-transparent bg-transparent hover:bg-app-surface-hover'
                            }`}
                          >
                            <Tag color={PERF_METHOD_COLORS[step.method]} className="m-0 shrink-0">{step.method}</Tag>
                            <span className="min-w-0 flex-1">
                              <span className={`block truncate text-xs ${activeStep ? 'font-semibold text-app-accent' : 'text-app-surface-text'}`}>{step.name || '未命名接口'}</span>
                              <span className="block truncate font-mono text-[10px] text-app-surface-text-muted">{step.path || '/'}</span>
                            </span>
                          </button>
                        })}
                      </div>}
                    </div>
                  })}
                  {suite.cases.length === 0 ? <div className="rounded-lg border border-dashed border-app-surface-border px-3 py-5 text-center text-xs text-app-surface-text-muted">还没有用例。</div> : null}
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

              <div className="grid min-w-0 content-start gap-4">
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
                </Card> : !caseHydrated ? <Card size="small"><Empty description="用例加载中..." /></Card> : activeForm && selectedStep && selectedStepIndex !== null ? <>
                  <Card size="small">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Button type="text" size="small" icon={<ArrowLeftOutlined />} aria-label="返回用例" onClick={backToCase} />
                          <Tag color={PERF_METHOD_COLORS[selectedStep.method]} className="m-0">{selectedStep.method}</Tag>
                          <span className="truncate text-base font-semibold text-app-surface-text">{selectedStep.name || '未命名接口'}</span>
                          <Tag className="max-w-[180px] truncate">{activeCase.name}</Tag>
                          <Tag>接口 {selectedStepIndex + 1} / {activeForm.steps.length}</Tag>
                          {dirty ? <Tag color="warning">有未保存修改</Tag> : null}
                        </div>
                        <div className="mt-1 truncate font-mono text-xs text-app-surface-text-muted">{selectedStep.path || '/'}</div>
                      </div>
                      <Space size={6} wrap>
                        <Tooltip title="上移接口">
                          <Button size="small" type="text" icon={<ArrowUpOutlined />} aria-label="上移接口" disabled={!canWrite || selectedStepIndex === 0} onClick={() => moveSelectedStep(-1)} />
                        </Tooltip>
                        <Tooltip title="下移接口">
                          <Button size="small" type="text" icon={<ArrowDownOutlined />} aria-label="下移接口" disabled={!canWrite || selectedStepIndex === activeForm.steps.length - 1} onClick={() => moveSelectedStep(1)} />
                        </Tooltip>
                        <Popconfirm
                          title="删除这个接口？"
                          okText="删除"
                          cancelText="取消"
                          disabled={!canWrite}
                          onConfirm={removeSelectedStep}
                        >
                          <Tooltip title="删除接口">
                            <Button size="small" type="text" danger icon={<DeleteOutlined />} aria-label="删除接口" disabled={!canWrite} />
                          </Tooltip>
                        </Popconfirm>
                        <Button size="small" icon={<CodeOutlined />} onClick={() => setInternalDataOpen(true)}>内部数据</Button>
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
                    {formErrorsAlert}
                  </Card>

                  <Card
                    size="small"
                    title={<span className="inline-flex items-center gap-2"><ApiOutlined />接口内容</span>}
                  >
                    <PerfStepFields
                      step={selectedStep}
                      stepIndex={selectedStepIndex}
                      variables={variablesBeforeStep(activeForm.steps, selectedStepIndex)}
                      disabled={!canWrite}
                      onChange={updateSelectedStep}
                    />
                  </Card>
                </> : activeForm ? <>
                  <Card size="small">
                    <div className="flex flex-wrap items-end justify-between gap-3">
                      <div className="flex min-w-0 flex-1 flex-wrap items-end gap-3">
                        <label className="grid min-w-[180px] flex-1 gap-1 text-xs text-app-surface-text-muted">
                          <span>用例名称<span className="text-app-request-error-text"> *</span></span>
                          <Input
                            size="small"
                            aria-label="用例名称"
                            value={activeForm.name}
                            status={activeForm.name.trim() ? undefined : 'error'}
                            disabled={!canWrite}
                            onChange={(event) => applyForm({ ...activeForm, name: event.target.value })}
                          />
                        </label>
                        <Tooltip title="停用后仍保留历史运行">
                          <label className="flex items-center gap-2 pb-1 text-xs text-app-surface-text-muted">
                            <span>启用</span>
                            <Switch
                              size="small"
                              aria-label="启用用例"
                              checked={activeForm.enabled}
                              disabled={!canWrite}
                              onChange={(enabled) => applyForm({ ...activeForm, enabled })}
                            />
                          </label>
                        </Tooltip>
                        <div className="flex items-center gap-2 pb-1">
                          <Tag>v{activeCase.version}</Tag>
                          <Tag>{activeForm.steps.length} 个接口</Tag>
                          {dirty ? <Tag color="warning">有未保存修改</Tag> : null}
                        </div>
                      </div>
                      <Space size={6} wrap>
                        <Button size="small" icon={<PlusOutlined />} disabled={!canWrite} onClick={addStep}>添加接口</Button>
                        <Button size="small" icon={<CodeOutlined />} onClick={() => setInternalDataOpen(true)}>内部数据</Button>
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
                    {formErrorsAlert}
                  </Card>

                  <PerfLoadModelForm
                    value={activeForm.load}
                    stepCount={activeForm.steps.length}
                    disabled={!canWrite}
                    onChange={load => applyForm({ ...activeForm, load })}
                  />
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
                </> : <Card size="small" title="无法进入表单编辑">
                  <Alert
                    showIcon
                    type="error"
                    title="当前性能用例 YAML 无法解析"
                    description="表单无法读取 steps / load / data。请查看内部数据排查用例内容。"
                    className="mb-3"
                  />
                  <Button icon={<CodeOutlined />} onClick={() => setInternalDataOpen(true)}>查看内部数据</Button>
                </Card>}
              </div>

              <Space orientation="vertical" size={12} className="w-full self-start xl:sticky xl:top-4">
                <Card size="small" title={<span className="inline-flex items-center gap-2"><PlayCircleOutlined />运行</span>} extra={<Tag>串行</Tag>}>
                  <div className="grid gap-1.5">
                    {suite.cases.map((item, index) => <div key={item.caseId} className={`flex items-center gap-2 text-xs ${item.enabled ? '' : 'opacity-50'}`}>
                      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-app-surface-border bg-app-surface text-[11px]">{index + 1}</span>
                      <span className="min-w-0 flex-1 truncate">{item.name}</span>
                      {item.enabled ? null : <Tag>停用</Tag>}
                    </div>)}
                  </div>
                  <div className="mt-3 grid gap-2">
                    <Tooltip title={runBlockedReason}>
                      <ProjectActionButton
                        action="execute"
                        projectId={projectId}
                        type="primary"
                        block
                        operation="run"
                        icon={<PlayCircleOutlined />}
                        disabled={Boolean(runBlockedReason)}
                        onClick={() => setRunOpen(true)}
                      >
                        运行测试集
                      </ProjectActionButton>
                    </Tooltip>
                    <Button block icon={<HistoryOutlined />} onClick={() => navigate(`/performance/runs?suiteId=${suiteId}`)}>运行记录</Button>
                  </div>
                  {activeForm ? <div className="mt-3 grid gap-1.5 border-t border-app-surface-border pt-3 text-xs">
                    <div className="flex justify-between gap-3"><span className="text-app-surface-text-muted">当前用例负载</span><span className="text-right font-semibold text-app-surface-text">{formatPerfLoadSummary(activeForm.load)}</span></div>
                    <div className="flex justify-between gap-3"><span className="text-app-surface-text-muted">接口数</span><span className="font-semibold text-app-surface-text">{activeForm.steps.length} 个</span></div>
                    <div className="flex justify-between gap-3"><span className="text-app-surface-text-muted">提取变量</span><span className="font-semibold text-app-surface-text">{extractVariables.length} 个</span></div>
                  </div> : null}
                  {dirty ? <div className="mt-3 rounded-lg border border-app-warning-border bg-app-warning-surface px-2.5 py-2 text-[11px] text-app-surface-text-muted">
                    当前用例有未保存修改；运行时会使用已保存版本。
                  </div> : null}
                  <div className="mt-3 rounded-lg border border-app-surface-border bg-app-surface-hover px-2.5 py-2 text-[11px] text-app-surface-text-muted">
                    平台只展示执行数据，不判定是否达标。
                  </div>
                </Card>

                <Card size="small" title={<span className="inline-flex items-center gap-2"><KeyOutlined />变量作用域</span>} extra={<Tag>用例内</Tag>}>
                  <div className="text-[11px] text-app-surface-text-muted">提取变量只在当前用例的当前 VU / 当前迭代内有效；下一个用例不会继承。</div>
                  {variables.length === 0 ? <div className="mt-2 text-xs text-app-surface-text-muted">还没有配置提取变量。</div> : <div className="mt-2 grid gap-1.5">
                    {variables.slice(0, 6).map((item) => <div key={`${item.caseId}-${item.stepIndex}-${item.name}`} className="min-w-0 rounded-md border border-app-surface-border px-2 py-1.5">
                      <div className="truncate font-mono text-[11px] text-app-accent">{`{{var.${item.name}}}`}</div>
                      <div className="truncate text-[11px] text-app-surface-text-muted">{item.caseName} · 步骤 {item.stepIndex + 1} {item.stepName}</div>
                    </div>)}
                    {variables.length > 6 ? <div className="text-[11px] text-app-surface-text-muted">还有 {variables.length - 6} 个变量，进入用例查看。</div> : null}
                  </div>}
                </Card>

                <Card size="small" title={<span className="inline-flex items-center gap-2"><DatabaseOutlined />当前用例数据</span>} extra={<Tag>{activeDataFiles.length} 个</Tag>}>
                  {activeDataFiles.length === 0 ? <div className="text-xs text-app-surface-text-muted">还没有数据文件。</div> : <div className="grid gap-1.5">
                    {activeDataFiles.map((file) => <div key={file.fileId} className="flex items-center gap-2 rounded-md border border-app-surface-border px-2 py-1.5">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs" title={file.filename}>{file.filename}</span>
                        <span className="block text-[11px] text-app-surface-text-muted">{file.size} B</span>
                      </span>
                      <Button type="text" size="small" aria-label={`下载 ${file.filename}`} onClick={() => void downloadFile(file)}>下载</Button>
                    </div>)}
                  </div>}
                  <div className="mt-2 text-[11px] text-app-surface-text-muted">数据文件只在当前用例内使用，不会跨用例共享。</div>
                </Card>
              </Space>
            </div>
          </> : null}
        </section>
      </div>

      <Modal
        title="内部数据"
        open={internalDataOpen}
        onCancel={() => setInternalDataOpen(false)}
        destroyOnHidden
        width={900}
        footer={<Button onClick={() => setInternalDataOpen(false)}>关闭</Button>}
      >
        <Alert
          showIcon
          type="info"
          title="这是表单生成的运行契约"
          description="普通用户在页面上只编辑表单；YAML 仅用于排查和与 Worker 契约对照。"
          className="mb-3"
        />
        <TextCodeEditor value={yaml} readOnly language="yaml" height={520} ariaLabel="内部运行契约" />
      </Modal>

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

      <PerfSuiteDrawer
        open={suiteDrawerOpen}
        editing={suite ?? null}
        saving={updateSuiteMutation.isPending}
        onClose={() => setSuiteDrawerOpen(false)}
        onSubmit={async (values) => {
          try {
            await updateSuiteMutation.mutateAsync(values)
          } catch {
            // mutation.onError 已经给出反馈。
          }
        }}
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
