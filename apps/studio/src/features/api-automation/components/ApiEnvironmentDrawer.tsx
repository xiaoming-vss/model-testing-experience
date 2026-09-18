import { ProjectActionModal } from '@/features/projects/components/ProjectActionModal'
import { ProjectActionButton } from '@/features/projects/components/ProjectActionButton'
import { SearchOutlined } from '@ant-design/icons'
import {
  Alert,
  Button,
  Card,
  Drawer,
  Empty,
  Form,
  Input,
  Popconfirm,
  Pagination,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  listItems,
  type ApiEnvironment,
  type ApiEnvironmentVar,
  type CreateApiEnvironmentPayload,
  type CreateApiEnvironmentVarPayload,
} from '@/services/api'
import {
  getErrorMessage,
  normalizeEnvironmentId,
  normalizeEnvironmentVarId,
} from '@/utils/format'
import { buildApiEnvironmentUpdatePayload, buildApiEnvironmentVarUpdatePayload } from '@/utils/updatePayload'
import { message } from '@/shared/utils/feedback'

const { Paragraph, Text } = Typography

type EnvironmentFormValues = CreateApiEnvironmentPayload
type EnvironmentVarFormValues = CreateApiEnvironmentVarPayload

export function ApiEnvironmentDrawer({
  open,
  projectId,
  currentEnvironmentId,
  onClose,
  onSelectEnvironment,
}: {
  open: boolean
  projectId?: string
  currentEnvironmentId?: string
  onClose: () => void
  onSelectEnvironment: (environmentId?: string) => void
}) {
  const queryClient = useQueryClient()
  const [environmentModalOpen, setEnvironmentModalOpen] = useState(false)
  const [environmentVarModalOpen, setEnvironmentVarModalOpen] = useState(false)
  const [editingEnvironment, setEditingEnvironment] = useState<ApiEnvironment | null>(null)
  const [editingEnvironmentVar, setEditingEnvironmentVar] = useState<ApiEnvironmentVar | null>(null)
  const [environmentVarSearch, setEnvironmentVarSearch] = useState('')
  const [environmentVarPage, setEnvironmentVarPage] = useState(1)
  const [environmentVarPageSize, setEnvironmentVarPageSize] = useState(8)
  const [environmentForm] = Form.useForm<EnvironmentFormValues>()
  const [environmentVarForm] = Form.useForm<EnvironmentVarFormValues>()

  const environmentsQuery = useQuery({
    queryKey: ['apiEnvironments', projectId],
    queryFn: () => api.getApiEnvironments(projectId!),
    enabled: open && Boolean(projectId),
  })
  const environments = listItems(environmentsQuery.data)
  const selectedEnvironment =
    environments.find((environment) => normalizeEnvironmentId(environment) === currentEnvironmentId) ??
    environments.find((environment) => environment.isDefault) ??
    environments[0]

  const environmentVarsQuery = useQuery({
    queryKey: ['apiEnvironmentVars', normalizeEnvironmentId(selectedEnvironment ?? { environmentId: '' } as ApiEnvironment)],
    queryFn: () => api.getApiEnvironmentVars(normalizeEnvironmentId(selectedEnvironment!)),
    enabled: open && Boolean(selectedEnvironment),
  })
  const environmentVars = useMemo(() => environmentVarsQuery.data ?? [], [environmentVarsQuery.data])
  const filteredEnvironmentVars = useMemo(() => {
    const keyword = environmentVarSearch.trim().toLowerCase()
    if (!keyword) return environmentVars

    return environmentVars.filter((item) =>
      [item.varKey, item.value, item.description]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(keyword)),
    )
  }, [environmentVarSearch, environmentVars])
  const pagedEnvironmentVars = useMemo(
    () => filteredEnvironmentVars.slice((environmentVarPage - 1) * environmentVarPageSize, environmentVarPage * environmentVarPageSize),
    [environmentVarPage, environmentVarPageSize, filteredEnvironmentVars],
  )
  const selectedEnvironmentKey = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined

  useEffect(() => {
    setEnvironmentVarPage(1)
    setEnvironmentVarSearch('')
  }, [selectedEnvironmentKey])

  useEffect(() => {
    const totalPages = Math.max(1, Math.ceil(filteredEnvironmentVars.length / environmentVarPageSize))
    if (environmentVarPage > totalPages) {
      setEnvironmentVarPage(totalPages)
    }
  }, [environmentVarPage, environmentVarPageSize, filteredEnvironmentVars.length])

  useEffect(() => {
    if (!open) return
    const nextEnvironmentId = selectedEnvironment ? normalizeEnvironmentId(selectedEnvironment) : undefined
    if (nextEnvironmentId !== currentEnvironmentId) {
      onSelectEnvironment(nextEnvironmentId)
    }
  }, [currentEnvironmentId, onSelectEnvironment, open, selectedEnvironment])

  const saveEnvironmentMutation = useMutation({
    mutationFn: (values: EnvironmentFormValues) => {
      if (!projectId) throw new Error('请先选择项目')
      if (editingEnvironment) {
        return api.updateApiEnvironment(
          normalizeEnvironmentId(editingEnvironment),
          buildApiEnvironmentUpdatePayload(editingEnvironment, values),
        )
      }
      return api.createApiEnvironment(projectId, values)
    },
    onSuccess: (environment) => {
      message.success(editingEnvironment ? '环境已更新' : '环境已创建')
      setEnvironmentModalOpen(false)
      setEditingEnvironment(null)
      environmentForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['apiEnvironments', projectId] })
      if (environment) onSelectEnvironment(normalizeEnvironmentId(environment))
    },
  })

  const deleteEnvironmentMutation = useMutation({
    mutationFn: (environmentId: string) => api.deleteApiEnvironment(environmentId),
    onSuccess: (_, environmentId) => {
      message.success('环境已删除')
      queryClient.invalidateQueries({ queryKey: ['apiEnvironments', projectId] })
      queryClient.removeQueries({ queryKey: ['apiEnvironmentVars', environmentId] })
      if (currentEnvironmentId === environmentId) onSelectEnvironment(undefined)
    },
  })

  const activateEnvironmentMutation = useMutation({
    mutationFn: async (environmentId: string) => {
      const nextEnvironment = environments.find((environment) => normalizeEnvironmentId(environment) === environmentId)
      if (!nextEnvironment) throw new Error('未找到环境')

      const currentActiveEnvironment = environments.find((environment) => environment.isDefault)
      const currentActiveEnvironmentId = currentActiveEnvironment ? normalizeEnvironmentId(currentActiveEnvironment) : undefined
      const requests: Array<Promise<unknown>> = []

      if (currentActiveEnvironmentId && currentActiveEnvironmentId !== environmentId) {
        requests.push(api.updateApiEnvironment(currentActiveEnvironmentId, { isDefault: false }))
      }
      if (!nextEnvironment.isDefault) {
        requests.push(api.updateApiEnvironment(environmentId, { isDefault: true }))
      }

      if (requests.length > 0) await Promise.all(requests)
      return environmentId
    },
    onMutate: async (environmentId) => {
      const previousEnvironmentId = currentEnvironmentId
      onSelectEnvironment(environmentId)
      return { previousEnvironmentId }
    },
    onError: (error, _environmentId, context) => {
      onSelectEnvironment(context?.previousEnvironmentId)
      message.error(getErrorMessage(error))
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['apiEnvironments', projectId] })
    },
  })

  const saveEnvironmentVarMutation = useMutation({
    mutationFn: (values: EnvironmentVarFormValues) => {
      if (!selectedEnvironment) throw new Error('请先选择环境')
      if (editingEnvironmentVar) {
        return api.updateApiEnvironmentVar(
          normalizeEnvironmentVarId(editingEnvironmentVar),
          buildApiEnvironmentVarUpdatePayload(editingEnvironmentVar, values),
        )
      }
      return api.createApiEnvironmentVar(normalizeEnvironmentId(selectedEnvironment), values)
    },
    onSuccess: () => {
      message.success(editingEnvironmentVar ? '变量已更新' : '变量已创建')
      setEnvironmentVarModalOpen(false)
      setEditingEnvironmentVar(null)
      environmentVarForm.resetFields()
      if (selectedEnvironment) {
        queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', normalizeEnvironmentId(selectedEnvironment)] })
      }
    },
  })

  const deleteEnvironmentVarMutation = useMutation({
    mutationFn: (envVarId: string) => api.deleteApiEnvironmentVar(envVarId),
    onSuccess: () => {
      message.success('变量已删除')
      if (selectedEnvironment) {
        queryClient.invalidateQueries({ queryKey: ['apiEnvironmentVars', normalizeEnvironmentId(selectedEnvironment)] })
      }
    },
  })

  function footerRange(total: number, currentPage: number, currentPageSize: number) {
    if (total === 0) return '显示第 0 条 - 第 0 条，共 0 条'
    const start = (currentPage - 1) * currentPageSize + 1
    const end = Math.min(currentPage * currentPageSize, total)
    return `显示第 ${start} 条 - 第 ${end} 条，共 ${total} 条`
  }

  const variableColumns: TableProps<ApiEnvironmentVar>['columns'] = [
    {
      title: '变量名',
      dataIndex: 'varKey',
      width: 180,
      render: (value: string, row) => (
        <Space size={8}>
          <span>{value}</span>
          {row.isSecret ? <Tag color="gold">Secret</Tag> : null}
        </Space>
      ),
    },
    {
      title: '变量值',
      dataIndex: 'value',
      width: 360,
      ellipsis: true,
      render: (value: string, row) => {
        const displayValue = row.isSecret ? '••••••••' : value || '-'

        return (
          <Tooltip title={row.isSecret ? undefined : displayValue} placement="topLeft">
            <span className="api-environment-var-value-cell">{displayValue}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '操作',
      width: 132,
      render: (_, row) => (
        <Space size={4}>
          <Tooltip title="编辑变量">
            <ProjectActionButton action="write"
              type="text"
              shape="circle"
              className="action-btn-update"
              operation="edit" iconOnly
              aria-label="编辑变量"
              onClick={() => openEditEnvironmentVar(row)}
            />
          </Tooltip>
          <Popconfirm title="确认删除该变量？" onConfirm={() => deleteEnvironmentVarMutation.mutate(normalizeEnvironmentVarId(row))}>
            <Tooltip title="删除变量">
              <ProjectActionButton action="write"
                danger
                type="text"
                shape="circle"
                className="action-btn-delete"
                operation="delete" iconOnly
                aria-label="删除变量"
                loading={deleteEnvironmentVarMutation.isPending}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  function openCreateEnvironment() {
    setEditingEnvironment(null)
    environmentForm.setFieldsValue({
      name: '',
      baseUrl: '',
      description: '',
      isDefault: environments.length === 0,
    })
    setEnvironmentModalOpen(true)
  }

  function openEditEnvironment(environment: ApiEnvironment) {
    setEditingEnvironment(environment)
    environmentForm.setFieldsValue({
      name: environment.name,
      baseUrl: environment.baseUrl,
      description: environment.description,
      isDefault: environment.isDefault,
    })
    setEnvironmentModalOpen(true)
  }

  function openCreateEnvironmentVar() {
    setEditingEnvironmentVar(null)
    environmentVarForm.setFieldsValue({
      varKey: '',
      value: '',
      description: '',
      isSecret: false,
    })
    setEnvironmentVarModalOpen(true)
  }

  function openEditEnvironmentVar(environmentVar: ApiEnvironmentVar) {
    setEditingEnvironmentVar(environmentVar)
    environmentVarForm.setFieldsValue({
      varKey: environmentVar.varKey,
      value: environmentVar.value,
      description: environmentVar.description,
      isSecret: environmentVar.isSecret,
    })
    setEnvironmentVarModalOpen(true)
  }

  return (
    <>
      <Drawer
        title="API 环境管理"
        open={open}
        size={960}
        onClose={onClose}
        className="api-environment-drawer"
      >
        <div className="api-environment-drawer-shell">
          {!projectId ? <Alert showIcon type="info" title="请先选择项目后再管理环境" /> : null}
          {environmentsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentsQuery.error)} /> : null}
          {environmentVarsQuery.error ? <Alert showIcon type="error" title={getErrorMessage(environmentVarsQuery.error)} /> : null}

          <div className="api-environment-split-layout">
            <section className="api-environment-section api-environment-section-top">
              <div className="api-environment-section-head">
                <div>
                  <Text strong>项目环境</Text>
                  <Paragraph type="secondary" className="api-environment-subtitle">
                    环境绑定当前项目，主要用于 API 测试时的 Base URL 和变量上下文。
                  </Paragraph>
                </div>
                <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!projectId} onClick={openCreateEnvironment}>
                  新建环境
                </ProjectActionButton>
              </div>

              <div className="api-environment-section-body api-environment-section-scrollable">
                {environments.length === 0 ? (
                  <Card className="api-environment-empty-card">
                    <Empty description="当前项目还没有 API 环境" />
                  </Card>
                ) : (
                  <div className="api-environment-list">
                    {environments.map((environment) => {
                      const environmentId = normalizeEnvironmentId(environment)
                      const active = environmentId === normalizeEnvironmentId(selectedEnvironment ?? ({ environmentId: '' } as ApiEnvironment))

                      return (
                        <div
                          key={environmentId}
                          className={`api-environment-item${active ? ' active' : ''}`}
                          onClick={() => onSelectEnvironment(environmentId)}
                        >
                          <div className="api-environment-item-main">
                            <div className="api-environment-item-top">
                              <Space size={8}>
                                <Text strong>{environment.name}</Text>
                              </Space>
                              <Space size={2}>
                                <Button
                                  type={active ? 'default' : 'primary'}
                                  size="small"
                                  loading={activateEnvironmentMutation.isPending}
                                  disabled={active}
                                  onClick={(event) => {
                                    event.stopPropagation()
                                    if (!active) activateEnvironmentMutation.mutate(environmentId)
                                  }}
                                >
                                  {active ? '使用中' : '启用'}
                                </Button>
                                <ProjectActionButton action="write"
                                  type="text"
                                  className="action-btn-update"
                                  operation="edit" iconOnly
                                  onClick={(event) => {
                                    event.stopPropagation()
                                    openEditEnvironment(environment)
                                  }}
                                />
                                <Popconfirm
                                  title="确认删除该环境？"
                                  onConfirm={() => deleteEnvironmentMutation.mutate(environmentId)}
                                >
                                  <ProjectActionButton action="write"
                                    danger
                                    type="text"
                                    className="action-btn-delete"
                                    operation="delete" iconOnly
                                    loading={deleteEnvironmentMutation.isPending}
                                    onClick={(event) => event.stopPropagation()}
                                  />
                                </Popconfirm>
                              </Space>
                            </div>
                            <div className="api-environment-item-url">{environment.baseUrl}</div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </section>

            <section className="api-environment-section api-environment-section-bottom">
              <div className="api-environment-section-head">
                <div className="api-environment-section-title-block">
                  <Text strong>环境变量</Text>
                  <Paragraph type="secondary" className="api-environment-subtitle">
                    变量会作为 API 测试运行时上下文。
                  </Paragraph>
                </div>
                <div className="api-environment-toolbar">
                  <span className="api-environment-current-pill">
                    启用环境：{selectedEnvironment?.name ?? '未选择'}
                  </span>
                  <Input
                    allowClear
                    className="api-environment-var-search"
                    prefix={<SearchOutlined />}
                    placeholder="搜索变量名 / 变量值"
                    value={environmentVarSearch}
                    onChange={(event) => {
                      setEnvironmentVarSearch(event.target.value)
                      setEnvironmentVarPage(1)
                    }}
                    disabled={!selectedEnvironment}
                  />
                  <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" disabled={!selectedEnvironment} onClick={openCreateEnvironmentVar}>
                    新建变量
                  </ProjectActionButton>
                </div>
              </div>

              <div className="api-environment-section-body api-environment-section-scrollable">
                {!selectedEnvironment ? (
                  <Card className="api-environment-empty-card">
                    <Empty description="请先选择环境" />
                  </Card>
                ) : (
                  <Card className="api-environment-vars-card">
                    <div className="table-body-scroll api-environment-vars-scroll">
                      <Table<ApiEnvironmentVar>
                        rowKey={normalizeEnvironmentVarId}
                        loading={environmentVarsQuery.isLoading}
                        dataSource={pagedEnvironmentVars}
                        columns={variableColumns}
                        pagination={false}
                        locale={{ emptyText: <Empty description={environmentVarSearch.trim() ? '没有匹配到变量' : '当前环境还没有变量'} /> }}
                      />
                    </div>
                    <div className="table-footer api-environment-vars-footer">
                      <Text type="secondary">{footerRange(filteredEnvironmentVars.length, environmentVarPage, environmentVarPageSize)}</Text>
                      <Pagination
                        current={environmentVarPage}
                        pageSize={environmentVarPageSize}
                        total={filteredEnvironmentVars.length}
                        showSizeChanger
                        onChange={(page, pageSize) => {
                          setEnvironmentVarPage(page)
                          setEnvironmentVarPageSize(pageSize)
                        }}
                      />
                    </div>
                  </Card>
                )}
              </div>
            </section>
          </div>
        </div>
      </Drawer>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title={editingEnvironment ? '编辑环境' : '新建环境'}
        open={environmentModalOpen}
        onCancel={() => {
          setEnvironmentModalOpen(false)
          setEditingEnvironment(null)
          environmentForm.resetFields()
        }}
        onOk={() => environmentForm.submit()}
        confirmLoading={saveEnvironmentMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
      >
        {saveEnvironmentMutation.error ? <Alert showIcon type="error" title={getErrorMessage(saveEnvironmentMutation.error)} /> : null}
          <Form<EnvironmentFormValues> form={environmentForm} layout="vertical" onFinish={(values) => saveEnvironmentMutation.mutate(values)} requiredMark={false}>
          <Form.Item name="name" label="环境名称" rules={[{ required: true, message: '请输入环境名称' }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="baseUrl" label="Base URL" rules={[{ required: true, message: '请输入 Base URL' }]}>
            <Input maxLength={512} placeholder="https://api.example.com" />
          </Form.Item>
          <Form.Item name="description" label="环境描述">
            <Input.TextArea rows={4} maxLength={256} />
          </Form.Item>
          <Form.Item name="isDefault" hidden valuePropName="checked">
            <Switch disabled={Boolean(editingEnvironmentVar?.isSecret)} />
          </Form.Item>
        </Form>
      </ProjectActionModal>

      <ProjectActionModal action="write"
        mask={{ closable: false }}
        title={editingEnvironmentVar ? '编辑变量' : '新建变量'}
        open={environmentVarModalOpen}
        onCancel={() => {
          setEnvironmentVarModalOpen(false)
          setEditingEnvironmentVar(null)
          environmentVarForm.resetFields()
        }}
        onOk={() => environmentVarForm.submit()}
        confirmLoading={saveEnvironmentVarMutation.isPending}
        okButtonProps={{ className: 'action-btn-save' }}
      >
        {saveEnvironmentVarMutation.error ? <Alert showIcon type="error" title={getErrorMessage(saveEnvironmentVarMutation.error)} /> : null}
        <Form<EnvironmentVarFormValues>
          form={environmentVarForm}
          layout="vertical"
          onFinish={(values) => saveEnvironmentVarMutation.mutate(values)}
          requiredMark={false}
        >
          <Form.Item name="varKey" label="变量名" rules={[{ required: true, message: '请输入变量名' }]}>
            <Input maxLength={100} />
          </Form.Item>
          <Form.Item extra={editingEnvironmentVar?.isSecret ? '保持 ******** 表示不修改密钥；只有保存者可修改和使用。其他成员需配置自己的环境。' : undefined} name="value" label="变量值" rules={[{ required: true, message: '请输入变量值' }]}>
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="description" label="变量描述">
            <Input.TextArea rows={3} maxLength={256} />
          </Form.Item>
          <Form.Item name="isSecret" label="敏感变量" valuePropName="checked">
            <Switch disabled={Boolean(editingEnvironmentVar?.isSecret)} />
          </Form.Item>
        </Form>
      </ProjectActionModal>
    </>
  )
}
