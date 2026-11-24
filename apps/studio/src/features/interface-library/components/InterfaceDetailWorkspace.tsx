import { SoftwareRepositoryTree } from './SoftwareRepositoryTree'
import { InterfaceEditorCard } from './InterfaceEditorCard'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'

export function InterfaceDetailWorkspace({ page }: { page: InterfaceDetailPageModel }) {
  const {
    draft,
    repositories,
    repositoriesQuery,
    canWrite,
    navigate,
    openCreateGroup,
    openRenameGroup,
    openRemoveGroup,
    openMoveInterface,
  } = page

  if (!draft) return null

  return (
    <div className="if-detail-shell flex min-h-0 min-w-0 flex-auto gap-3">
      <SoftwareRepositoryTree
        view={page.treeView}
        repositories={repositories}
        loading={repositoriesQuery.isLoading}
        selectedSoftwareRepositoryId={draft.softwareRepositoryId}
        selectedInterfaceId={draft.interfaceId}
        mode="detail"
        canManageInterfaces={canWrite}
        onSelectRepository={() => undefined}
        onShowAll={() => navigate('/asset-library?tab=interfaces')}
        onOpenInterface={id => navigate(`/asset-library/interfaces/${id}`)}
        onCreateGroup={openCreateGroup}
        onRenameGroup={openRenameGroup}
        onRemoveGroup={openRemoveGroup}
        onMoveInterface={openMoveInterface}
      />

      <main className="if-detail-main flex min-h-0 min-w-0 flex-auto">
        <InterfaceEditorCard page={page} />
      </main>
    </div>
  )
}
