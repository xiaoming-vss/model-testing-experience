import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Spin } from 'antd'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { listItems } from '@/services/api'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiApp, ApiInterfaceListItem } from '../types'
import '@/shared/styles/surface-tokens.css'
import '../styles/index.css'

/**
 * 接口库入口：不再渲染外层接口表格，直接进入“应用树 + 接口编辑器”工作区。
 * 优先打开当前应用下最近更新的接口；没有接口时进入该应用的新建接口页。
 */
export function InterfaceLibraryPage() {
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const [searchParams] = useSearchParams()
  const appId = searchParams.get('appId') ?? ''
  const paneActive = usePaneActive()

  const appsQuery = useQuery({
    queryKey: ['apiApps', projectId],
    queryFn: () => interfaceLibraryApi.getApiApps(projectId),
    enabled: Boolean(projectId) && paneActive,
  })
  const interfacesQuery = useQuery({
    queryKey: ['apiInterfaces', 'entry', projectId, appId],
    queryFn: () =>
      interfaceLibraryApi.getProjectApiInterfaces(projectId, {
        appId,
        page: 1,
        pageSize: 1,
      }),
    enabled: Boolean(projectId) && paneActive,
  })

  const apps = listItems(appsQuery.data) as ApiApp[]
  const firstInterface = (listItems(interfacesQuery.data) as ApiInterfaceListItem[])[0]

  // Hidden asset tabs stay mounted. Never redirect while another tab is visible.
  if (!paneActive) return null

  if (!projectId) {
    return (
      <div className="workbench-page interface-library-page tp-surface">
        <Alert type="info" showIcon title="请先在顶部选择一个项目" />
      </div>
    )
  }

  if (appsQuery.isLoading || interfacesQuery.isLoading || interfacesQuery.isFetching) {
    return (
      <div className="workbench-page interface-library-page tp-surface if-detail-loading">
        <Spin />
      </div>
    )
  }

  if (appsQuery.isError || interfacesQuery.isError) {
    return (
      <div className="workbench-page interface-library-page tp-surface">
        <Alert
          type="error"
          showIcon
          title="接口库加载失败"
          description="请检查当前项目权限后重试。"
          action={
            <Button
              onClick={() => {
                void interfacesQuery.refetch()
                void appsQuery.refetch()
              }}
            >
              重试
            </Button>
          }
        />
      </div>
    )
  }

  if (firstInterface) {
    return <Navigate to={`/asset-library/interfaces/${firstInterface.interfaceId}`} replace />
  }

  const requestedApp = apps.find(app => app.appId === appId)
  const targetApp = requestedApp ?? apps.find(app => app.enabled) ?? apps[0]
  const target = targetApp
    ? `/asset-library/interfaces/new?appId=${encodeURIComponent(targetApp.appId)}`
    : '/asset-library/interfaces/new'
  return <Navigate to={target} replace />
}
