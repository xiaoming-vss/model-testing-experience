import { useEffect, useMemo, useState } from 'react'
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
import type { PerfCaseSummary } from '../types'
import { buildDefaultPerfYaml } from '../utils/perf'
import { PerfCaseDrawer, type PerfCaseFormValues } from '../components/PerfCaseDrawer'
import { StartPerfRunModal } from '../components/StartPerfRunModal'

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
  const [editingCase, setEditingCase] = useState<PerfCaseSummary | null>(null)
  const [runCase, setRunCase] = useState<PerfCaseSummary | null>(null)
  const [environmentDrawerOpen, setEnvironmentDrawerOpen] = useState(false)
  const [selectedEnvironmentId, setSelectedEnvironmentId] = useState<string | undefined>(undefined)

  const casesQuery = useQuery({
    queryKey: ['perfCases', activeProjectId],
    queryFn: () => api.listPerfCases(activeProjectId!),
    enabled: Boolean(activeProjectId),
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

  const filteredCases = useMemo(() => {
    const text = keyword.trim().toLowerCase()
    return listItems(casesQuery.data).filter((perfCase) => {
      const matchesKeyword = !text || `${perfCase.name} ${perfCase.description}`.toLowerCase().includes(text)
      const matchesStatus = status === 'all' || (status === 'enabled' ? perfCase.enabled : !perfCase.enabled)
      return matchesKeyword && matchesStatus
    })
  }, [casesQuery.data, keyword, status])
  const pagedCases = useMemo(
    () => filteredCases.slice((page - 1) * pageSize, page * pageSize),
    [filteredCases, page, pageSize],
  )

  useEffect(() => {
    const maxPage = Math.max(1, Math.ceil(filteredCases.length / pageSize))
    if (page > maxPage) setPage(maxPage)
  }, [filteredCases.length, page, pageSize])

  const saveCaseMutation = useMutation({
    mutationFn: ({ editing, values }: { editing: PerfCaseSummary | null; values: PerfCaseFormValues }) => {
      if (!activeProjectId) throw new Error('请先选择项目')
      if (editing) {
        return api.updatePerfCase(editing.caseId, {
          name: values.name.trim(),
          description: values.description?.trim() ?? '',
          enabled: values.enabled,
        })
      }
      const name = values.name.trim()
      return api.createPerfCase(activeProjectId, {
        name,
        description: values.description?.trim() ?? '',
        yaml: buildDefaultPerfYaml(name),
      })
    },
    onSuccess: async (perfCase, variables) => {
      message.success(variables.editing ? '性能用例已更新' : '性能用例已创建')
      setDrawerOpen(false)
      setEditingCase(null)
      await queryClient.invalidateQueries({ queryKey: ['perfCases', activeProjectId] })
      if (!variables.editing) navigate(`/performance/cases/${perfCase.caseId}`)
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  const deleteCaseMutation = useMutation({
    mutationFn: (caseId: string) => api.deletePerfCase(caseId),
    onSuccess: () => {
      message.success('性能用例已删除')
      queryClient.invalidateQueries({ queryKey: ['perfCases', activeProjectId] })
    },
    onError: (error) => message.error(getErrorMessage(error)),
  })

  async function submitCase(values: PerfCaseFormValues) {
    try {
      await saveCaseMutation.mutateAsync({ editing: editingCase, values })
    } catch {
      // mutation.onError 已经给出反馈；保留 Drawer 让用户修正。
    }
  }

  function renderCaseCard(perfCase: PerfCaseSummary) {
    const title = <Link to={`/performance/cases/${perfCase.caseId}`} title={perfCase.name}>{perfCase.name}</Link>
    return <EntityCard
      key={perfCase.caseId}
      title={title}
      status={<Tag color={perfCase.enabled ? 'success' : 'default'}>{perfCase.enabled ? '已启用' : '已停用'}</Tag>}
      meta={[
        { label: '数据文件', value: `${perfCase.dataFiles.length} 个` },
        { label: '用例版本', value: `v${perfCase.version}` },
      ]}
      footerNote={<>最近更新 {formatTime(perfCase.updatedAt)}</>}
      actions={<>
        <Tooltip title={resolvedEnvironmentId ? '发起运行' : '请先选择性能环境'}>
          <ProjectActionButton
            action="execute"
            projectId={activeProjectId}
            type="text"
            shape="circle"
            className="action-btn-read"
            operation="run"
            iconOnly
            aria-label="发起运行"
            disabled={!resolvedEnvironmentId}
            onClick={() => setRunCase(perfCase)}
          />
        </Tooltip>
        <Tooltip title="编辑用例信息">
          <ProjectActionButton
            action="write"
            projectId={activeProjectId}
            type="text"
            shape="circle"
            className="action-btn-update"
            operation="edit"
            iconOnly
            aria-label="编辑用例信息"
            onClick={() => { setEditingCase(perfCase); setDrawerOpen(true) }}
          />
        </Tooltip>
        <Popconfirm title="确认删除该性能用例？" onConfirm={() => deleteCaseMutation.mutate(perfCase.caseId)}>
          <Tooltip title="删除用例">
            <ProjectActionButton
              action="write"
              projectId={activeProjectId}
              type="text"
              shape="circle"
              className="action-btn-delete"
              operation="delete"
              iconOnly
              danger
              aria-label="删除用例"
              loading={deleteCaseMutation.isPending && deleteCaseMutation.variables === perfCase.caseId}
            />
          </Tooltip>
        </Popconfirm>
      </>}
      onOpen={() => navigate(`/performance/cases/${perfCase.caseId}`)}
    >
      <p className={`entity-card-desc${perfCase.description ? '' : ' is-empty'}`} title={perfCase.description}>
        {perfCase.description || '暂无性能用例描述'}
      </p>
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
                    placeholder="搜索用例名称 / 描述"
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
                  onClick={() => { setEditingCase(null); setDrawerOpen(true) }}
                >
                  新建性能用例
                </ProjectActionButton>
              </Space>
            </div>
          </div>

          {environmentsQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
          {casesQuery.isError ? <Alert showIcon type="error" title={getErrorMessage(casesQuery.error)} /> : null}

          <div className="api-test-card-body tp-list-body">
            <div className="sprint-card-scroll api-test-card-scroll tp-list-scroll">
              {casesQuery.isPending ? (
                <div className="sprint-card-loading"><Empty description="性能用例加载中..." image={Empty.PRESENTED_IMAGE_SIMPLE} /></div>
              ) : filteredCases.length === 0 ? (
                <div className="sprint-card-loading">
                  <Empty
                    image={<AppstoreOutlined />}
                    description={<Space orientation="vertical" size={4}>
                      <Text strong>{keyword.trim() ? '没有符合搜索条件的性能用例' : '当前项目还没有性能用例'}</Text>
                      <Text type="secondary">
                        {keyword.trim() ? '换个关键词，或者清空搜索看全部用例。' : '创建用例后进入 YAML 编辑器，配置步骤、负载和验收标准。'}
                      </Text>
                    </Space>}
                  >
                    {keyword.trim()
                      ? <Button onClick={() => setKeyword('')}>清空搜索</Button>
                      : <ProjectActionButton action="write" projectId={activeProjectId} type="primary" className="action-btn-create" operation="create" onClick={() => { setEditingCase(null); setDrawerOpen(true) }}>
                        新建性能用例
                      </ProjectActionButton>}
                  </Empty>
                </div>
              ) : (
                <div className="entity-card-grid">{pagedCases.map(renderCaseCard)}</div>
              )}
            </div>
            <div className="table-footer api-test-footer">
              <ListPagination
                loading={casesQuery.isFetching || casesQuery.isError}
                current={page}
                pageSize={pageSize}
                total={filteredCases.length}
                onChange={(nextPage, nextPageSize) => {
                  setPage(nextPage)
                  setPageSize(nextPageSize)
                }}
              />
            </div>
          </div>
        </section>
      </div>

      <PerfCaseDrawer
        open={drawerOpen}
        editing={editingCase}
        saving={saveCaseMutation.isPending}
        onClose={() => { setDrawerOpen(false); setEditingCase(null) }}
        onSubmit={submitCase}
      />
      <StartPerfRunModal
        open={Boolean(runCase)}
        projectId={activeProjectId}
        perfCase={runCase}
        defaultEnvironmentId={resolvedEnvironmentId}
        onClose={() => setRunCase(null)}
        onStarted={(run) => navigate(`/performance/runs/${run.runId}`)}
        onManageEnvironments={() => { setRunCase(null); setEnvironmentDrawerOpen(true) }}
        onManageMonitoring={() => { setRunCase(null); navigate('/base-services?tab=monitoring') }}
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
