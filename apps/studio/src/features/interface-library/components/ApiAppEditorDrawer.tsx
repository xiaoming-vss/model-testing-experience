import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Drawer, Input, Select, Switch } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { ApiError, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp } from '../types'

type Props = {
  open: boolean
  projectId: string
  app: ApiApp | null
  onClose: () => void
  onSaved: (app: ApiApp) => void
}

type AppForm = {
  name: string
  description: string
  basePath: string
  enabled: boolean
}

const emptyForm: AppForm = { name: '', description: '', basePath: '', enabled: true }

/** 应用创建/编辑抽屉；入口在接口库左侧应用树中，不再有独立应用页面。 */
export function ApiAppEditorDrawer({ open, projectId, app, onClose, onSaved }: Props) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<AppForm>(emptyForm)
  const [repoConnectionId, setRepoConnectionId] = useState('')
  const [repoGroupId, setRepoGroupId] = useState('')
  const [repoRepositoryId, setRepoRepositoryId] = useState('')
  const [clearRepository, setClearRepository] = useState(false)

  const connectionsQuery = useQuery({
    queryKey: ['gitlabConnections', projectId],
    queryFn: () => baseServicesApi.getGitlabConnections(projectId),
    enabled: Boolean(projectId) && open,
  })
  const bindingsQuery = useQuery({
    queryKey: ['gitlabProjectBindings', projectId],
    queryFn: () => baseServicesApi.getGitlabProjectBindings(projectId),
    enabled: Boolean(projectId) && open,
  })
  const repositoriesQuery = useQuery({
    queryKey: ['gitlabGroupRepositories', projectId, repoConnectionId, repoGroupId],
    queryFn: () => baseServicesApi.getGitlabGroupRepositories(projectId, repoConnectionId, repoGroupId),
    enabled: Boolean(projectId && repoConnectionId && repoGroupId && open),
  })

  const connections = listItems(connectionsQuery.data).filter(
    connection => connection.status === 'active',
  )
  const groupBindings = useMemo(() => {
    const selectedConnection = connections.find(connection => connection.connectionId === repoConnectionId)
    const instance = (selectedConnection?.baseUrl ?? '').replace(/\/+$/, '')
    return listItems(bindingsQuery.data).filter(binding => {
      const provider = binding.provider
      const resourceType = binding.remoteResourceType ?? binding.remote_resource_type
      const status = binding.status
      if (provider !== 'gitlab' || resourceType !== 'group' || status !== 'active') return false
      if (!instance) return true
      return (binding.instanceUrl ?? '').replace(/\/+$/, '') === instance
    })
  }, [bindingsQuery.data, connections, repoConnectionId])
  const repositories = listItems(repositoriesQuery.data)

  useEffect(() => {
    if (!open) return
    if (app) {
      setForm({
        name: app.name,
        description: app.description,
        basePath: app.basePath,
        enabled: app.enabled,
      })
      setClearRepository(false)
    } else {
      setForm(emptyForm)
    }
    setRepoConnectionId('')
    setRepoGroupId('')
    setRepoRepositoryId('')
  }, [app, open])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const repository =
        !clearRepository && repoConnectionId && repoGroupId && repoRepositoryId
          ? {
              connectionId: repoConnectionId,
              groupId: repoGroupId,
              repositoryId: repoRepositoryId,
            }
          : undefined
      if (app) {
        return interfaceLibraryApi.updateApiApp(app.appId, {
          name: form.name.trim(),
          description: form.description,
          basePath: form.basePath,
          enabled: form.enabled,
          ...(clearRepository ? { repository: null } : repository ? { repository } : {}),
        })
      }
      return interfaceLibraryApi.createApiApp(projectId, {
        name: form.name.trim(),
        description: form.description,
        basePath: form.basePath,
        enabled: form.enabled,
        repository: repository ?? null,
      })
    },
    onSuccess: saved => {
      message.success(app ? '应用已保存' : '应用已创建')
      queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
      onSaved(saved)
    },
    onError: error => message.error(errorMessage(error)),
  })

  return (
    <Drawer
      open={open}
      title={app ? '编辑应用' : '新建应用'}
      size={520}
      onClose={onClose}
      destroyOnHidden
      footer={
        <div className="if-drawer-footer">
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={saveMutation.isPending}
            disabled={!form.name.trim()}
            onClick={() => saveMutation.mutate()}
          >
            保存
          </Button>
        </div>
      }
    >
      <div className="if-app-form">
        <label>
          <span>应用名称</span>
          <Input
            value={form.name}
            maxLength={100}
            placeholder="例如：订单服务"
            onChange={event => setForm({ ...form, name: event.target.value })}
          />
        </label>
        <label>
          <span>描述</span>
          <Input.TextArea
            value={form.description}
            rows={3}
            maxLength={512}
            placeholder="应用用途说明"
            onChange={event => setForm({ ...form, description: event.target.value })}
          />
        </label>
        <label>
          <span>base path</span>
          <Input
            value={form.basePath}
            maxLength={512}
            placeholder="例如：/api/v2"
            onChange={event => setForm({ ...form, basePath: event.target.value })}
          />
        </label>
        <label className="if-switch-row">
          <span>启用应用</span>
          <Switch
            checked={form.enabled}
            onChange={value => setForm({ ...form, enabled: value })}
          />
        </label>

        <div className="if-repository-section">
          <div className="if-repository-head">
            <span>代码仓库</span>
            {app?.repository?.path ? <code>{app.repository.path}</code> : null}
          </div>
          {app?.repository ? (
            <label className="if-checkbox-row">
              <input
                type="checkbox"
                checked={clearRepository}
                onChange={event => setClearRepository(event.target.checked)}
              />
              清除当前仓库关联
            </label>
          ) : null}
          <div className="if-repository-selects">
            <Select
              aria-label="选择 GitLab 连接"
              placeholder="GitLab 连接"
              value={repoConnectionId || undefined}
              disabled={clearRepository}
              loading={connectionsQuery.isLoading}
              options={connections.map(connection => ({
                label: connection.name,
                value: connection.connectionId,
              }))}
              onChange={value => {
                setRepoConnectionId(value)
                setRepoGroupId('')
                setRepoRepositoryId('')
              }}
            />
            <Select
              aria-label="选择 GitLab 群组"
              placeholder="项目绑定的群组"
              value={repoGroupId || undefined}
              disabled={clearRepository || !repoConnectionId}
              loading={bindingsQuery.isLoading}
              options={groupBindings.map(binding => ({
                label: binding.remoteNameSnapshot || binding.remoteResourceId || '群组',
                value: binding.remoteResourceId ?? binding.remote_resource_id ?? '',
              }))}
              onChange={value => {
                setRepoGroupId(value)
                setRepoRepositoryId('')
              }}
            />
            <Select
              aria-label="选择代码仓库"
              placeholder="代码仓库"
              value={repoRepositoryId || undefined}
              disabled={clearRepository || !repoGroupId}
              loading={repositoriesQuery.isLoading}
              showSearch
              optionFilterProp="label"
              options={repositories.map(repository => ({
                label: repository.pathWithNamespace || repository.path || repository.name || String(repository.id),
                value: String(repository.id),
              }))}
              onChange={setRepoRepositoryId}
            />
          </div>
          {!connections.length && open ? (
            <div className="if-repository-hint">
              暂无可用 GitLab 连接，可先创建不带仓库的应用。
            </div>
          ) : null}
        </div>
      </div>
    </Drawer>
  )
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return getErrorMessage(error)
}
