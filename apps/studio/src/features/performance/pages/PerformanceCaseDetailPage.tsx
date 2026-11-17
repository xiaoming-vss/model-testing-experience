import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { parse } from 'yaml'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  DownloadOutlined,
  HistoryOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Empty,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from 'antd'
import type { UploadProps } from 'antd'
import { TextCodeEditor } from '@/shared/components/TextCodeEditor/TextCodeEditor'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { useProjectAccess } from '@/features/projects/hooks/useProjectAccess'
import { EnvironmentDrawer } from '@/features/projects/components/EnvironmentDrawer'
import { api, listItems } from '@/services/api'
import { downloadStoredFile, uploadStoredFile } from '@/shared/api/files'
import { saveBlob } from '@/shared/utils/download'
import { message } from '@/shared/utils/feedback'
import { formatTime, getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { PerfDataFile } from '../types'
import {
  PERF_OUTCOME_LABELS,
  PERF_STATUS_LABELS,
  isPerfRunActive,
  perfStatusColor,
} from '../utils/perf'
import { PerfCaseDrawer, type PerfCaseFormValues } from '../components/PerfCaseDrawer'
import { StartPerfRunModal } from '../components/StartPerfRunModal'

const { Paragraph, Text } = Typography

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function validateYaml(text: string) {
  if (!text.trim()) return 'YAML 不能为空'
  try {
    const parsed = parse(text) as Record<string, unknown> | null
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return 'YAML 根节点必须是映射'
    if (parsed.specVersion !== '1.0') return 'specVersion 必须是字符串 "1.0"'
    if (!parsed.case || typeof parsed.case !== 'object') return '缺少 case 节点'
    return ''
  } catch (error) {
    return error instanceof Error ? error.message : 'YAML 解析失败'
  }
}

export function PerformanceCaseDetailPage() {
  const { caseId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [yaml, setYaml] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [dataFiles, setDataFiles] = useState<PerfDataFile[]>([])
  const [hydratedCaseId, setHydratedCaseId] = useState('')
  const [caseDrawerOpen, setCaseDrawerOpen] = useState(false)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)
  const [runModalOpen, setRunModalOpen] = useState(false)
  const [uploading, setUploading] = useState(false)

  const caseQuery = useQuery({
    queryKey: ['perfCase', caseId],
    queryFn: () => api.getPerfCase(caseId),
    enabled: Boolean(caseId),
  })
  const perfCase = caseQuery.data
  const projectId = perfCase?.projectId
  const { can } = useProjectAccess(projectId ?? '')
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
  const recentRunsQuery = useQuery({
    queryKey: ['perfCaseRuns', caseId],
    queryFn: () => api.listPerfRuns(projectId!, { caseId, page: 1, pageSize: 5 }),
    enabled: Boolean(projectId),
  })

  useEffect(() => {
    if (!perfCase || hydratedCaseId === perfCase.caseId) return
    setYaml(perfCase.yaml)
    setEnabled(perfCase.enabled)
    setDataFiles(perfCase.dataFiles)
    setHydratedCaseId(perfCase.caseId)
  }, [hydratedCaseId, perfCase])

  const yamlError = useMemo(() => validateYaml(yaml), [yaml])
  const dirty = Boolean(perfCase && (yaml !== perfCase.yaml || enabled !== perfCase.enabled))

  const saveMutation = useMutation({
    mutationFn: () => api.updatePerfCase(caseId, { yaml, enabled }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['perfCase', caseId], updated)
      queryClient.invalidateQueries({ queryKey: ['perfCases', updated.projectId] })
      message.success('性能用例已保存')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const saveInfoMutation = useMutation({
    mutationFn: (values: PerfCaseFormValues) => api.updatePerfCase(caseId, {
      name: values.name.trim(),
      description: values.description?.trim() ?? '',
      enabled: values.enabled,
    }),
    onSuccess: async (updated) => {
      queryClient.setQueryData(['perfCase', caseId], updated)
      await queryClient.invalidateQueries({ queryKey: ['perfCases', updated.projectId] })
      setEnabled(updated.enabled)
      setCaseDrawerOpen(false)
      message.success('用例信息已更新')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const removeDataFileMutation = useMutation({
    mutationFn: (fileId: string) => api.updatePerfCase(caseId, {
      yaml,
      dataFileIds: dataFiles.filter((item) => item.fileId !== fileId).map((item) => item.fileId),
    }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['perfCase', caseId], updated)
      queryClient.invalidateQueries({ queryKey: ['perfCases', updated.projectId] })
      setDataFiles(updated.dataFiles)
      setYaml(updated.yaml)
      message.success('数据文件已移除')
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function uploadDataFile(file: File) {
    if (!projectId) return
    if (!/\.(csv|json)$/i.test(file.name)) {
      message.warning('数据文件仅支持 CSV / JSON')
      return
    }
    setUploading(true)
    try {
      const fileId = await uploadStoredFile(projectId, file, 'perf_case_data')
      const updated = await api.updatePerfCase(caseId, {
        yaml,
        dataFileIds: [...dataFiles.map((item) => item.fileId), fileId],
      })
      queryClient.setQueryData(['perfCase', caseId], updated)
      queryClient.invalidateQueries({ queryKey: ['perfCases', updated.projectId] })
      setDataFiles(updated.dataFiles)
      setYaml(updated.yaml)
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
    disabled: uploading || !can('write'),
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

  const recentRuns = listItems(recentRunsQuery.data)

  return <ProjectAccessScope projectId={projectId ?? ''}>
    {caseQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(caseQuery.error)} /> : null}
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board">
          <div className="tp-list-toolbar flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <Button type="text" icon={<ArrowLeftOutlined />} aria-label="返回性能测试" onClick={() => navigate('/testing?tab=perf')} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="tp-list-title">{perfCase?.name ?? '性能用例'}</h1>
                  {perfCase ? <Tag>v{perfCase.version}</Tag> : null}
                  {perfCase ? <Tag color={enabled ? 'success' : 'default'}>{enabled ? '已启用' : '已停用'}</Tag> : null}
                  {dirty ? <Tag color="warning">有未保存修改</Tag> : null}
                </div>
                <div className="mt-1 text-xs text-app-surface-text-muted">
                  最后保存于 {formatTime(perfCase?.updatedAt)}
                </div>
              </div>
            </div>
            <Space size={8} wrap>
              <Select
                className="min-w-[150px]"
                value={resolvedEnvironmentId}
                options={environments.map((environment) => ({
                  label: `${environment.name}${environment.isDefault ? '（默认）' : ''}`,
                  value: normalizeEnvironmentId(environment),
                }))}
                loading={environmentsQuery.isLoading}
                placeholder="选择性能环境"
                onChange={setSelectedEnvironmentId}
                disabled={!projectId || environments.length === 0}
              />
              <Button icon={<HistoryOutlined />} onClick={() => navigate(`/performance/runs?caseId=${caseId}`)}>
                运行记录
              </Button>
              <Button onClick={() => setCaseDrawerOpen(true)} disabled={!perfCase}>编辑信息</Button>
              <ProjectActionButton
                action="write"
                projectId={projectId}
                operation="save"
                disabled={!dirty || Boolean(yamlError) || saveMutation.isPending}
                loading={saveMutation.isPending}
                onClick={() => saveMutation.mutate()}
              >
                保存
              </ProjectActionButton>
              <Tooltip title={dirty ? '请先保存 YAML 再发起运行' : !perfCase?.enabled ? '用例已停用' : !resolvedEnvironmentId ? '请先选择性能环境' : ''}>
                <ProjectActionButton
                  action="execute"
                  projectId={projectId}
                  type="primary"
                  operation="run"
                  disabled={dirty || !perfCase?.enabled || !resolvedEnvironmentId}
                  onClick={() => setRunModalOpen(true)}
                >
                  发起运行
                </ProjectActionButton>
              </Tooltip>
            </Space>
          </div>

          {caseQuery.isPending ? <div className="p-10"><Empty description="性能用例加载中..." /></div> : perfCase ? (
            <div className="grid grid-cols-1 gap-4 p-4 xl:grid-cols-[minmax(0,1fr)_340px]">
              <Card styles={{ body: { padding: 0 } }} className="overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-app-surface-border bg-app-surface-hover px-3 py-2">
                  <Space size={8}>
                    <Tag color="blue">YAML</Tag>
                    <Text strong>case.yaml</Text>
                  </Space>
                  <Space size={8}>
                    {yamlError
                      ? <Text type="danger" className="text-xs">{yamlError}</Text>
                      : <Text type="success" className="text-xs">校验通过</Text>}
                  </Space>
                </div>
                <TextCodeEditor
                  value={yaml}
                  onChange={setYaml}
                  language="yaml"
                  height="clamp(520px, calc(100vh - 330px), 760px)"
                  minHeight={480}
                  ariaLabel="性能用例 YAML 编辑器"
                />
                <div className="flex items-center justify-between border-t border-app-surface-border bg-app-surface-hover px-3 py-1.5 text-xs text-app-surface-text-muted">
                  <span>UTF-8 · YAML</span>
                  <span>{yaml.split('\n').length} 行</span>
                </div>
              </Card>

              <Space orientation="vertical" size={12} className="w-full">
                <Card size="small" title="用例信息">
                  <Paragraph className="mb-3 text-xs text-app-surface-text-muted">
                    {perfCase.description || '暂无性能用例描述'}
                  </Paragraph>
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div>
                      <Text strong>启用用例</Text>
                      <div className="text-xs text-app-surface-text-muted">停用后仍保留历史运行</div>
                    </div>
                    <Switch checked={enabled} disabled={!can('write')} onChange={setEnabled} />
                  </div>
                  <Space orientation="vertical" size={4} className="w-full text-xs">
                    <div className="flex justify-between gap-3"><Text type="secondary">最近更新</Text><Text>{formatTime(perfCase.updatedAt)}</Text></div>
                    <div className="flex justify-between gap-3"><Text type="secondary">数据文件</Text><Text>{dataFiles.length} 个</Text></div>
                  </Space>
                </Card>

                <Card
                  size="small"
                  title="数据文件"
                  extra={<Upload {...uploadProps}><Button size="small" icon={<UploadOutlined />} loading={uploading}>上传</Button></Upload>}
                >
                  <Space orientation="vertical" size={8} className="w-full">
                    {dataFiles.length === 0 ? <Text type="secondary" className="text-xs">暂无数据文件。上传前请先在 YAML 的 case.data 中声明 source。</Text> : dataFiles.map((file) => (
                      <div key={file.fileId} className="flex items-center gap-2 rounded-md border border-app-surface-border px-2 py-1.5">
                        <Tag color={file.filename.endsWith('.json') ? 'gold' : 'green'}>{file.filename.endsWith('.json') ? 'JSON' : 'CSV'}</Tag>
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-xs" title={file.filename}>{file.filename}</div>
                          <div className="text-[11px] text-app-surface-text-muted">{formatBytes(file.size)}</div>
                        </div>
                        <Tooltip title="下载">
                          <Button type="text" size="small" icon={<DownloadOutlined />} aria-label={`下载 ${file.filename}`} onClick={() => void downloadFile(file)} />
                        </Tooltip>
                        <Popconfirm
                          title="移除这个数据文件？"
                          description="YAML 仍在引用该文件时不能移除；请先在编辑器中删除对它的引用。"
                          okText="移除"
                          cancelText="取消"
                          onConfirm={() => removeDataFileMutation.mutate(file.fileId)}
                        >
                          <Tooltip title="移除数据文件">
                            <Button
                              type="text"
                              size="small"
                              danger
                              disabled={!can('write')}
                              loading={removeDataFileMutation.isPending && removeDataFileMutation.variables === file.fileId}
                              icon={<DeleteOutlined />}
                              aria-label={`移除 ${file.filename}`}
                            />
                          </Tooltip>
                        </Popconfirm>
                      </div>
                    ))}
                  </Space>
                  <div className="mt-2 text-[11px] text-app-surface-text-muted">仅支持 CSV / JSON；上传或移除会同时保存当前 YAML。单个用例最多 20 个文件、总计 100 MB。</div>
                </Card>

                <Card size="small" title="最近运行" extra={<Button type="link" size="small" onClick={() => navigate(`/performance/runs?caseId=${caseId}`)}>全部</Button>}>
                  {recentRunsQuery.isError ? <Text type="danger" className="text-xs">{getErrorMessage(recentRunsQuery.error)}</Text> : recentRunsQuery.isPending ? <Text type="secondary" className="text-xs">加载中...</Text> : recentRuns.length === 0
                    ? <Text type="secondary" className="text-xs">这个用例还没有运行记录。</Text>
                    : <Space orientation="vertical" size={8} className="w-full">
                      {recentRuns.map((run) => <Link key={run.runId} to={`/performance/runs/${run.runId}`} className="block rounded-md border border-app-surface-border px-2 py-1.5 hover:bg-app-surface-hover">
                        <div className="flex items-center justify-between gap-2">
                          <Tag color={perfStatusColor(run.status)}>{PERF_STATUS_LABELS[run.status]}</Tag>
                          <span className="text-[11px] text-app-surface-text-muted">{formatTime(run.startedAt ?? run.createdAt)}</span>
                        </div>
                        <div className="mt-1 truncate text-xs">
                          {run.outcome ? PERF_OUTCOME_LABELS[run.outcome] : '未判定'} · {run.environmentName}
                        </div>
                        {isPerfRunActive(run.status) ? <div className="mt-0.5 text-[11px] text-app-surface-text-muted">运行中的状态会自动刷新</div> : null}
                      </Link>)}
                    </Space>}
                </Card>
              </Space>
            </div>
          ) : null}
        </section>
      </div>

      <PerfCaseDrawer
        open={caseDrawerOpen}
        editing={perfCase ?? null}
        saving={saveInfoMutation.isPending}
        onClose={() => setCaseDrawerOpen(false)}
        onSubmit={async (values) => {
          try {
            await saveInfoMutation.mutateAsync(values)
          } catch {
            // mutation.onError 已反馈，保留 Drawer。
          }
        }}
      />
      <StartPerfRunModal
        open={runModalOpen}
        projectId={projectId}
        perfCase={perfCase ?? null}
        defaultEnvironmentId={resolvedEnvironmentId}
        onClose={() => setRunModalOpen(false)}
        onStarted={(run) => {
          void queryClient.invalidateQueries({ queryKey: ['perfCaseRuns', caseId] })
          navigate(`/performance/runs/${run.runId}`)
        }}
        onManageEnvironments={() => { setRunModalOpen(false); setEnvironmentDrawerOpen(true) }}
        onManageMonitoring={() => { setRunModalOpen(false); navigate('/base-services?tab=monitoring') }}
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
