import { useEffect, useMemo, useState } from 'react'
import '@/shared/styles/surface-tokens.css'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppstoreOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons'
import { Alert, Button, Empty, Input, Popconfirm, Select, Space, Tag, Tooltip, Typography } from 'antd'
import { EntityCard } from '@/shared/components/EntityCard'
import { ListPagination } from '@/shared/components/ListPagination'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { ProjectAccessScope } from '@/features/projects/components/ProjectAccessScope'
import { EnvironmentDrawer } from '@/features/projects/components/EnvironmentDrawer'
import { useActiveProject } from '@/features/projects/hooks/useActiveProject'
import { api, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { DEFAULT_PAGE_SIZE } from '@/shared/utils/pagination'
import { formatTime, getErrorMessage, normalizeEnvironmentId } from '@/utils/format'
import type { PerfSuiteSummary } from '../types'
import { PERF_OUTCOME_LABELS, PERF_STATUS_LABELS, perfOutcomeColor, perfStatusColor } from '../utils/perf'
import { PERF_LOAD_MODEL_LABELS, type PerfLoadModel } from '../utils/perfLoadModel'
import { PerfSuiteDrawer, type PerfSuiteFormValues } from '../components/PerfSuiteDrawer'
import { StartPerfSuiteRunModal } from '../components/StartPerfSuiteRunModal'

const { Text } = Typography

export function PerformancePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { activeProjectId } = useActiveProject()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<'all' | 'enabled' | 'disabled'>('all')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingSuite, setEditingSuite] = useState<PerfSuiteSummary | null>(null)
  const [runSuite, setRunSuite] = useState<PerfSuiteSummary | null>(null)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)

  const suitesQuery = useQuery({
    queryKey: ['perfSuites', activeProjectId],
    queryFn: () => api.listPerfSuites(activeProjectId!),
    enabled: Boolean(activeProjectId),
  })
  const runSuiteQuery = useQuery({
    queryKey: ['perfSuite', runSuite?.suiteId],
    queryFn: () => api.getPerfSuite(runSuite!.suiteId),
    enabled: Boolean(runSuite),
  })
  const environmentsQuery = useQuery({
    queryKey: ['testEnvironments', activeProjectId, 'perf'],
    queryFn: () => api.getApiEnvironments(activeProjectId!, 'perf'),
    enabled: Boolean(activeProjectId),
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
    setPage(1)
  }, [activeProjectId, keyword, status])

  const filteredSuites = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return listItems(suitesQuery.data).filter((suite) => {
      const matchesKeyword = !text || `${suite.name} ${suite.description}`.toLowerCase().includes(text)
      const matchesStatus = status === 'all' || (status === 'enabled' ? suite.enabled : !suite.enabled)
      return matchesKeyword && matchesStatus
    })
  }, [suitesQuery.data, keyword, status])
  const pagedSuites = useMemo(
    () => filteredSuites.slice((page - 1) * pageSize, page * pageSize),
    [filteredSuites, page, pageSize],
  )

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredSuites.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [filteredSuites.length, page, pageSize])

  const saveSuiteMutation = useMutation({
    mutationFn: ({ editing, values }: { editing: PerfSuiteSummary | null; values: PerfSuiteFormValues }) => {
      if (!activeProjectId) throw new Error('请先选择项目')
      const body = {
        name: values.name.trim(),
        description: values.description?.trim() ?? '',
        enabled: values.enabled,
      }
      return editing ? api.updatePerfSuite(editing.suiteId, body) : api.createPerfSuite(activeProjectId, body)
    },
    onSuccess: async (suite, variables) => {
      message.success(variables.editing ? '性能测试集已更新' : '性能测试集已创建')
      setDrawerOpen(false)
      setEditingSuite(null)
      await queryClient.invalidateQueries({ queryKey: ['perfSuites', activeProjectId] })
      if (!variables.editing) navigate(`/performance/suites/${suite.suiteId}`)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteSuiteMutation = useMutation({
    mutationFn: (suiteId: string) => api.deletePerfSuite(suiteId),
    onSuccess: () => {
      message.success('性能测试集已删除')
      queryClient.invalidateQueries({ queryKey: ['perfSuites', activeProjectId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function submitSuite(values: PerfSuiteFormValues) {
    try {
      await saveSuiteMutation.mutateAsync({ editing: editingSuite, values })
    } catch {
      // mutation.onError 已经给出反馈；保留 Drawer 让用户修正。
    }
  }

  function renderSuiteCard(suite: PerfSuiteSummary) {
    const title = <Link to={`/performance/suites/${suite.suiteId}`} title={suite.name}>{suite.name}</Link>
    return <EntityCard
      key={suite.suiteId}
      title={title}
      status={<Tag color={suite.enabled ? 'success' : 'default'}>{suite.enabled ? '已启用' : '已停用'}</Tag>}
      meta={[
        { label: '用例', value: `${suite.enabledCaseCount}/${suite.caseCount} 启用` },
        { label: 'API 步骤', value: `${suite.stepCount} 个` },
      ]}
      footerNote={<div className="flex flex-wrap items-center gap-2">
        <span>最近更新 {formatTime(suite.updatedAt)}</span>
        {suite.lastRunStatus ? <>
          <span className="text-app-surface-text-muted">·</span>
          <Tag color={perfStatusColor(suite.lastRunStatus)}>{PERF_STATUS_LABELS[suite.lastRunStatus]}</Tag>
          {suite.lastRunOutcome ? <Tag color={perfOutcomeColor(suite.lastRunOutcome)}>{PERF_OUTCOME_LABELS[suite.lastRunOutcome]}</Tag> : <Tag>未判定</Tag>}
        </> : <span className="text-app-surface-text-muted">· 尚未运行</span>}
      </div>}
      actions={<>
        <Tooltip title={suite.enabledCaseCount > 0 ? '运行测试集' : '测试集没有启用的用例'}>
          <ProjectActionButton
            action="execute"
            projectId={activeProjectId}
            type="text"
            shape="circle"
            className="action-btn-read"
            operation="run"
            iconOnly
            aria-label="运行测试集"
            disabled={suite.enabledCaseCount === 0}
            onClick={() => setRunSuite(suite)}
          />
        </Tooltip>
        <Tooltip title="编辑测试集信息">
          <ProjectActionButton
            action="write"
            projectId={activeProjectId}
            type="text"
            shape="circle"
            className="action-btn-update"
            operation="edit"
            iconOnly
            aria-label="编辑测试集信息"
            onClick={() => { setEditingSuite(suite); setDrawerOpen(true) }}
          />
        </Tooltip>
        <Popconfirm
          title="确认删除该性能测试集？"
          description="测试集内的用例、运行记录和关联数据会一起删除。"
          onConfirm={() => deleteSuiteMutation.mutate(suite.suiteId)}
        >
          <Tooltip title="删除测试集">
            <ProjectActionButton
              action="write"
              projectId={activeProjectId}
              type="text"
              shape="circle"
              className="action-btn-delete"
              operation="delete"
              iconOnly
              danger
              aria-label="删除测试集"
              loading={deleteSuiteMutation.isPending && deleteSuiteMutation.variables === suite.suiteId}
            />
          </Tooltip>
        </Popconfirm>
      </>}
      onOpen={() => navigate(`/performance/suites/${suite.suiteId}`)}
    >
      <p className={`entity-card-desc${suite.description ? '' : ' is-empty'}`} title={suite.description}>
        {suite.description || '暂无测试集描述'}
      </p>
      {suite.loadModels.length > 0 || suite.dataFileCount > 0 ? <div className="mt-2 flex flex-wrap gap-1">
        {suite.loadModels.map((model) => <Tag key={model}>{PERF_LOAD_MODEL_LABELS[model as PerfLoadModel] ?? model}</Tag>)}
        {suite.dataFileCount > 0 ? <Tag>数据文件 {suite.dataFileCount}</Tag> : null}
      </div> : null}
    </EntityCard>
  }

  return <ProjectAccessScope projectId={activeProjectId ?? ''}>
    <div className="workbench-page api-automation-page functional-test-page tp-list-surface api-test-page tp-surface">
      <div className="api-automation-content">
        <section className="workbench-panel workbench-board-panel tp-board tp-list-panel">
          <div className="panel-header api-panel-header api-test-header tp-list-toolbar">
            <div className="api-test-header-main">
              <div className="requirement-panel-head api-panel-head-main">
                <h1 className="tp-list-title">性能测试</h1>
                <div className="api-filter-group">
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">环境</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={resolvedEnvironmentId}
                      options={environmentOptions}
                      loading={environmentsQuery.isLoading}
                      placeholder="选择性能环境"
                      onChange={setSelectedEnvironmentId}
                      disabled={!activeProjectId || environments.length === 0}
                    />
                  </div>
                  <div className="api-filter-field">
                    <span className="api-filter-field-label">状态</span>
                    <Select
                      className="api-filter-select business-filter-select"
                      value={status}
                      options={[
                        { value: 'all', label: '全部状态' },
                        { value: 'enabled', label: '已启用' },
                        { value: 'disabled', label: '已停用' },
                      ]}
                      onChange={setStatus}
                    />
                  </div>
                </div>
                <div className="api-test-search-field">
                  <Input
                    className="api-filter-input api-test-search-input"
                    allowClear
                    prefix={<SearchOutlined />}
                    placeholder="搜索测试集名称 / 描述"
                    value={keyword}
                    onChange={(event) => setKeyword(event.target.value)}
                  />
                </div>
              </div>
              <Space size={8} className="api-test-header-actions">
                <Button icon={<SettingOutlined />} disabled={!activeProjectId} onClick={() => setEnvironmentDrawerOpen(true)}>
                  环境管理
                </Button>
                <Button onClick={() => navigate('/performance/runs')}>运行记录</Button>
                <ProjectActionButton
                  action="write"
                  projectId={activeProjectId}
                  type="primary"
                  className="action-btn-create"
                  operation="create"
                  disabled={!activeProjectId}
                  onClick={() => { setEditingSuite(null); setDrawerOpen(true) }}
                >
                  新建测试集
                </ProjectActionButton>
              </Space>
            </div>
          </div>

          {environmentsQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
          {suitesQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(suitesQuery.error)} /> : null}

          <div className="api-test-card-body tp-list-body">
            <div className="sprint-card-scroll api-test-card-scroll tp-list-scroll">
              {suitesQuery.isPending ? (
                <div className="sprint-card-loading"><Empty description="性能测试集加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>
              ) : filteredSuites.length === 0 ? (
                <div className="sprint-card-loading">
                  <Empty
                    image={<AppstoreOutlined />}
                    description={<Space orientation="vertical" size={4}>
                      <Text strong>{keyword.trim() ? '没有符合搜索条件的性能测试集' : '当前项目还没有性能测试集'}</Text>
                      <Text type="secondary">
                        {keyword.trim() ? '换个关键词，或者清空搜索看全部测试集。' : '先创建测试集，再在测试集内添加按顺序串行执行的性能用例。'}
                      </Text>
                    </Space>}
                  >
                    {keyword.trim()
                      ? <Button onClick={() => setKeyword('')}>清空搜索</Button>
                      : <ProjectActionButton action="write" projectId={activeProjectId} type="primary" className="action-btn-create" operation="create" onClick={() => { setEditingSuite(null); setDrawerOpen(true) }}>
                        新建测试集
                      </ProjectActionButton>}
                  </Empty>
                </div>
              ) : (
                <div className="entity-card-grid">{pagedSuites.map(renderSuiteCard)}</div>
              )}
            </div>
            <div className="table-footer api-test-footer">
              <ListPagination
                loading={suitesQuery.isFetching || suitesQuery.isError}
                current={page}
                pageSize={pageSize}
                total={filteredSuites.length}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage)
                  setPageSize(nextPageSize)
                }}
              />
            </div>
          </div>
        </section>
      </div>

      <PerfSuiteDrawer
        open={drawerOpen}
        editing={editingSuite}
        saving={saveSuiteMutation.isPending}
        onClose={() => { setDrawerOpen(false); setEditingSuite(null) }}
        onSubmit={submitSuite}
      />
      <StartPerfSuiteRunModal
        open={Boolean(runSuite)}
        projectId={activeProjectId}
        suite={runSuiteQuery.data ?? null}
        defaultEnvironmentId={resolvedEnvironmentId}
        onClose={() => setRunSuite(null)}
        onStarted={(run) => navigate(`/performance/runs/${run.suiteRunId}`)}
        onManageEnvironments={() => { setRunSuite(null); setEnvironmentDrawerOpen(true) }}
        onManageMonitoring={() => { setRunSuite(null); navigate('/base-services?tab=monitoring') }}
      />
      <EnvironmentDrawer
        open={environmentDrawerOpen}
        projectId={activeProjectId}
        kind="perf"
        currentEnvironmentId={resolvedEnvironmentId}
        onClose={() => setEnvironmentDrawerOpen(false)}
        onSelectEnvironment={(environmentId) => setSelectedEnvironmentId(environmentId ?? '')}
      />
    </div>
  </ProjectAccessScope>
}
