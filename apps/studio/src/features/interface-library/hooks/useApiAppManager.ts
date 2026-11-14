import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Modal } from 'antd'
import { useMemo, useState } from 'react'
import { ApiError, listItems } from '@/services/api'
import { message } from '@/shared/utils/feedback'
import { getErrorMessage } from '@/utils/format'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp } from '../types'

/** 接口应用列表与应用级维护动作；接口库列表和详情共用。 */
export function useApiAppManager(projectId: string) {
  const queryClient = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingApp, setEditingApp] = useState<ApiApp | null>(null)

  const appsQuery = useQuery({
    queryKey: ['apiApps', projectId],
    queryFn: () => interfaceLibraryApi.getApiApps(projectId),
    enabled: Boolean(projectId),
  })
  const apps = useMemo(() => listItems(appsQuery.data) as ApiApp[], [appsQuery.data])

  const toggleMutation = useMutation({
    mutationFn: (app: ApiApp) =>
      interfaceLibraryApi.updateApiApp(app.appId, { enabled: !app.enabled }),
    onSuccess: () => {
      message.success('应用状态已更新')
      queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
    },
    onError: error => message.error(errorMessage(error)),
  })
  const deleteMutation = useMutation({
    mutationFn: (app: ApiApp) => interfaceLibraryApi.deleteApiApp(app.appId),
    onSuccess: () => {
      message.success('应用已删除')
      queryClient.invalidateQueries({ queryKey: ['apiApps', projectId] })
    },
    onError: error => message.error(errorMessage(error)),
  })

  function openCreate() {
    setEditingApp(null)
    setEditorOpen(true)
  }

  function openEdit(app: ApiApp) {
    setEditingApp(app)
    setEditorOpen(true)
  }

  function closeEditor() {
    setEditorOpen(false)
  }

  function toggleApp(app: ApiApp) {
    toggleMutation.mutate(app)
  }

  function deleteApp(app: ApiApp) {
    if (app.interfaceCount > 0) {
      message.info('请先删除该应用下的接口')
      return
    }
    Modal.confirm({
      title: '删除应用',
      content: `确定删除「${app.name}」吗？`,
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: () => deleteMutation.mutateAsync(app),
    })
  }

  return {
    apps,
    appsQuery,
    editorOpen,
    editingApp,
    openCreate,
    openEdit,
    closeEditor,
    toggleApp,
    deleteApp,
  }
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  return getErrorMessage(error)
}
