import { Alert, Button, Empty, Spin } from 'antd'
import { InterfaceDetailTopbar } from '../components/InterfaceDetailTopbar'
import { InterfaceDetailWorkspace } from '../components/InterfaceDetailWorkspace'
import { InterfaceGroupModals } from '../components/InterfaceGroupModals'
import { InterfaceOpenApiImportModal } from '../components/InterfaceOpenApiImportModal'
import { InterfaceWorkspaceShell } from '../components/InterfaceWorkspaceShell'
import { useInterfaceDetailPage } from '../hooks/useInterfaceDetailPage'
import { errorMessage } from '../utils/interfaceDetailForm'

export function InterfaceDetailPage() {
  const page = useInterfaceDetailPage()
  const {
    interfaceId,
    isCreate,
    draft,
    projectId,
    repositories,
    repositoriesQuery,
    interfaceInActiveProject,
    interfaceQuery,
    navigate,
  } = page

  if (interfaceId && interfaceQuery.isError) {
    return (
      <InterfaceWorkspaceShell>
        <Alert
          type="error"
          showIcon
          title="接口加载失败"
          description={errorMessage(interfaceQuery.error)}
          action={<Button onClick={() => navigate('/asset-library?tab=interfaces')}>返回接口库</Button>}
        />
      </InterfaceWorkspaceShell>
    )
  }

  if (!draft) {
    if (isCreate && !projectId) {
      return (
        <InterfaceWorkspaceShell>
          <Empty description="请先在顶部选择一个项目" />
        </InterfaceWorkspaceShell>
      )
    }
    if (isCreate && repositoriesQuery.isError) {
      return (
        <InterfaceWorkspaceShell>
          <Alert
            type="error"
            showIcon
            title="软件仓库加载失败"
            description="请检查当前项目权限后重试。"
            action={<Button onClick={() => void repositoriesQuery.refetch()}>重试</Button>}
          />
        </InterfaceWorkspaceShell>
      )
    }
    if (isCreate && !repositoriesQuery.isLoading && !repositories.length) {
      return (
        <InterfaceWorkspaceShell>
          <Empty description="当前项目还没有软件仓库，请先在「软件仓库」页创建。" />
        </InterfaceWorkspaceShell>
      )
    }
    return (
      <InterfaceWorkspaceShell className="if-detail-loading">
        <Spin />
      </InterfaceWorkspaceShell>
    )
  }

  if (!isCreate && !repositoriesQuery.isLoading && !interfaceInActiveProject) {
    return (
      <InterfaceWorkspaceShell>
        <Alert
          type="error"
          showIcon
          title="接口不属于当前项目"
          description="请切换回接口所属项目后重试。"
          action={<Button onClick={() => navigate('/asset-library?tab=interfaces')}>返回接口库</Button>}
        />
      </InterfaceWorkspaceShell>
    )
  }

  return (
    <InterfaceWorkspaceShell>
      <InterfaceDetailTopbar page={page} />
      <InterfaceDetailWorkspace page={page} />
      <InterfaceOpenApiImportModal page={page} />
      <InterfaceGroupModals page={page} />
    </InterfaceWorkspaceShell>
  )
}
