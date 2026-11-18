import { useQuery } from '@tanstack/react-query'
import { Alert, Button, Spin } from 'antd'
import { Navigate, useSearchParams } from 'react-router-dom'
import { useWorkbenchStore } from '@/features/projects/store/workbench.store'
import { listItems } from '@/services/api'
import { usePaneActive } from '@/shared/ui/paneActivity'
import { interfaceLibraryApi } from '../api/interfaceLibrary.api'
import type { ApiInterfaceListItem, SoftwareRepository } from '../types'
import '@/shared/styles/surface-tokens.css'
import styles from '../styles/interface-library.module.css'
import detailStyles from '../styles/interface-detail.module.css'

const interfaceScopes = `${styles.scope} ${detailStyles.scope}`

/**
 * 接口库入口：不渲染外层接口表格，直接进入“软件仓库树 + 接口编辑器”工作区。
 * 优先打开当前软件仓库下最近更新的接口；没有接口时进入该仓库的新建接口页。
 */
export function InterfaceLibraryPage() {
  const projectId = useWorkbenchStore(state => state.activeProjectId) ?? ''
  const [searchParams] = useSearchParams()
  const softwareRepositoryId = searchParams.get('softwareRepositoryId') ?? ''
  const paneActive = usePaneActive()

  const repositoriesQuery = useQuery({
    queryKey: ['softwareRepositories', projectId],
    queryFn: () => interfaceLibraryApi.getSoftwareRepositories(projectId),
    enabled: Boolean(projectId) && paneActive,
  })
  const interfacesQuery = useQuery({
    queryKey: ['apiInterfaces', 'entry', projectId, softwareRepositoryId],
    queryFn: () =>
      interfaceLibraryApi.getProjectApiInterfaces(projectId, {
        softwareRepositoryId,
        page: 1,
        pageSize: 1,
      }),
    enabled: Boolean(projectId) && paneActive,
  })

  const repositories = listItems(repositoriesQuery.data) as SoftwareRepository[]
  const firstInterface = (listItems(interfacesQuery.data) as ApiInterfaceListItem[])[0]

  // Hidden asset tabs stay mounted. Never redirect while another tab is visible.
  if (!paneActive) return null

  if (!projectId) {
    return (
      <div className={`workbench-page interface-library-page tp-surface ${styles.pageRoot} ${interfaceScopes}`}>
        <Alert type="info" showIcon title="请先在顶部选择一个项目" />
      </div>
    )
  }

  if (
    repositoriesQuery.isLoading ||
    interfacesQuery.isLoading ||
    interfacesQuery.isFetching
  ) {
    return (
      <div className={`workbench-page interface-library-page tp-surface if-detail-loading ${styles.pageRoot} ${interfaceScopes}`}>
        <Spin />
      </div>
    )
  }

  if (repositoriesQuery.isError || interfacesQuery.isError) {
    return (
      <div className={`workbench-page interface-library-page tp-surface ${styles.pageRoot} ${interfaceScopes}`}>
        <Alert
          type="error"
          showIcon
          title="接口库加载失败"
          description="请检查当前项目权限后重试。"
          action={
            <Button
              onClick={() => {
                void interfacesQuery.refetch()
                void repositoriesQuery.refetch()
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

  const requestedRepository = repositories.find(
    repository => repository.softwareRepositoryId === softwareRepositoryId,
  )
  const targetRepository = requestedRepository ?? repositories[0]
  const target = targetRepository
    ? `/asset-library/interfaces/new?softwareRepositoryId=${encodeURIComponent(targetRepository.softwareRepositoryId)}`
    : '/asset-library/interfaces/new'
  return <Navigate to={target} replace />
}
