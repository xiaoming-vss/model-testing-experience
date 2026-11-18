import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Drawer, Input, Select } from 'antd'
import { useEffect, useState } from 'react'
import { baseServicesApi } from '@/features/base-services/api/baseServices.api'
import { ApiError, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { SoftwareRepository } from '../types'
import styles from '../styles/interface-library.module.css'
import detailStyles from '../styles/interface-detail.module.css'
import editorStyles from '../styles/interface-editor.module.css'

const interfaceScopes = `${styles.scope} ${detailStyles.scope} ${editorStyles.scope}`

type Props = {
  open: boolean
  projectId: string
  repository: SoftwareRepository | null
  onClose: () => void
  onSaved: (repository: SoftwareRepository) => void
}

type RepositoryForm = {
  name: string
  description: string
  basePath: string
}

const emptyForm: RepositoryForm = { name: '', description: '', basePath: '' }

/** 软件仓库创建/编辑抽屉；入口在接口库左侧仓库树中。 */
export function SoftwareRepositoryEditorDrawer({
  open,
  projectId,
  repository,
  onClose,
  onSaved,
}: Props) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<RepositoryForm>(emptyForm)
  const [repoConnectionId, setRepoConnectionId] = useState('')
  const [repoGroupId, setRepoGroupId] = useState('')
  const [repoRepositoryId, setRepoRepositoryId] = useState('')
  const [repoGroupSearch, setRepoGroupSearch] = useState('')
  const [debouncedGroupSearch, setDebouncedGroupSearch] = useState('')

  const connectionsQuery = useQuery({
    queryKey: ['gitlabConnections', projectId],
    queryFn: () => baseServicesApi.getGitlabConnections(projectId),
    enabled: Boolean(projectId) && open,
  })
  const groupsQuery = useQuery({
    queryKey: ['gitlabGroups', projectId, repoConnectionId, debouncedGroupSearch],
    queryFn: () =>
      baseServicesApi.getGitlabGroups(projectId, repoConnectionId, debouncedGroupSearch),
    enabled: Boolean(projectId && repoConnectionId && open),
  })
  const repositoriesQuery = useQuery({
    queryKey: ['gitlabGroupRepositories', projectId, repoConnectionId, repoGroupId],
    queryFn: () =>
      baseServicesApi.getGitlabGroupRepositories(
        projectId,
        repoConnectionId,
        repoGroupId,
      ),
    enabled: Boolean(projectId && repoConnectionId && repoGroupId && open),
  })

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => setDebouncedGroupSearch(repoGroupSearch.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [open, repoGroupSearch])

  const connections = listItems(connectionsQuery.data).filter(
    connection => connection.status === 'active',
  )
  const groups = listItems(groupsQuery.data).filter(
    group => group.id !== undefined || Boolean(group.fullPath),
  )
  const repositories = listItems(repositoriesQuery.data)

  useEffect(() => {
    if (!open) return
    if (repository) {
      setForm({
        name: repository.name,
        description: repository.description,
        basePath: repository.basePath,
      })
    } else {
      setForm(emptyForm)
    }
    setRepoConnectionId('')
    setRepoGroupId('')
    setRepoRepositoryId('')
    setRepoGroupSearch('')
    setDebouncedGroupSearch('')
  }, [repository, open])

  const repositoryPayload =
    repoConnectionId && repoGroupId && repoRepositoryId
      ? {
          connectionId: repoConnectionId,
          groupId: repoGroupId,
          repositoryId: repoRepositoryId,
        }
      : undefined
  const repositorySelectionIncomplete =
    Boolean(repoConnectionId || repoGroupId || repoRepositoryId) && !repositoryPayload
  const canSave =
    Boolean(form.name.trim()) &&
    !repositorySelectionIncomplete &&
    (Boolean(repository) || Boolean(repositoryPayload))

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (repository) {
        return interfaceLibraryApi.updateSoftwareRepository(
          repository.softwareRepositoryId,
          {
            name: form.name.trim(),
            description: form.description,
            basePath: form.basePath,
            ...(repositoryPayload ? { repository: repositoryPayload } : {}),
          },
        )
      }
      if (!repositoryPayload) throw new Error('请选择代码仓库')
      return interfaceLibraryApi.createSoftwareRepository(projectId, {
        name: form.name.trim(),
        description: form.description,
        basePath: form.basePath,
        repository: repositoryPayload,
      })
    },
    onSuccess: saved => {
      message.success(repository ? '软件仓库已保存' : '软件仓库已创建')
      queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
      onSaved(saved)
    },
    onError: error => message.error(errorMessage(error)),
  })

  return (
    <Drawer
      rootClassName={interfaceScopes}
      open={open}
      title={repository ? '编辑软件仓库' : '新建软件仓库'}
      size={520}
      onClose={onClose}
      destroyOnHidden
      footer={
        <div className="if-drawer-footer">
          <Button onClick={onClose}>取消</Button>
          <Button
            type="primary"
            loading={saveMutation.isPending}
            disabled={!canSave}
            onClick={() => saveMutation.mutate()}
          >
            保存
          </Button>
        </div>
      }
    >
      <div className="if-app-form">
        <label>
          <span>软件仓库名称</span>
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
            placeholder="软件仓库用途说明"
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

        <div className="if-repository-section">
          <div className="if-repository-head">
            <span>代码仓库（必选）</span>
            {repository?.repository?.path ? <code>{repository.repository.path}</code> : null}
          </div>
          {repository ? (
            <div className="if-repository-hint">
              重新选择代码仓库会清除需求已填写的工作分支和基线分支。
            </div>
          ) : null}
          <div className="if-repository-selects">
            <Select
              aria-label="选择 GitLab 连接"
              placeholder="GitLab 连接"
              value={repoConnectionId || undefined}
              loading={connectionsQuery.isLoading}
              options={connections.map(connection => ({
                label: connection.name,
                value: connection.connectionId,
              }))}
              onChange={value => {
                setRepoConnectionId(value)
                setRepoGroupId('')
                setRepoRepositoryId('')
                setRepoGroupSearch('')
                setDebouncedGroupSearch('')
              }}
            />
            <Select
              aria-label="选择 GitLab 群组"
              placeholder="GitLab 群组"
              value={repoGroupId || undefined}
              disabled={!repoConnectionId}
              loading={groupsQuery.isLoading}
              showSearch
              filterOption={false}
              onSearch={setRepoGroupSearch}
              options={groups.map(group => {
                const value = String(group.id ?? group.fullPath ?? '')
                return {
                  label: group.fullPath || group.name || value || '群组',
                  value,
                }
              })}
              onChange={value => {
                setRepoGroupId(value)
                setRepoRepositoryId('')
              }}
            />
            <Select
              aria-label="选择代码仓库"
              placeholder="代码仓库"
              value={repoRepositoryId || undefined}
              disabled={!repoGroupId}
              loading={repositoriesQuery.isLoading}
              showSearch
              optionFilterProp="label"
              options={repositories.map(repository => ({
                label:
                  repository.pathWithNamespace ||
                  repository.path ||
                  repository.name ||
                  String(repository.id),
                value: String(repository.id),
              }))}
              onChange={setRepoRepositoryId}
            />
          </div>
          {repositorySelectionIncomplete ? (
            <div className="if-repository-hint">请完整选择连接、群组和代码仓库。</div>
          ) : null}
          {!connections.length && open ? (
            <div className="if-repository-hint">
              暂无可用 GitLab 连接，请先在项目基础服务中创建 GitLab 连接。
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
