import { useQueryClient } from '@tanstack/react-query'
import { OpenApiImportModal } from './OpenApiImportModal'
import type { InterfaceDetailPageModel } from '../hooks/useInterfaceDetailPage'

export function InterfaceOpenApiImportModal({ page }: { page: InterfaceDetailPageModel }) {
  const {
    importOpen,
    setImportOpen,
    repositories,
    draft,
    isCreate,
    interfaceId,
    navigate,
    interfaceQuery,
    projectId,
  } = page
  const queryClient = useQueryClient()

  if (!draft) return null

  return (
    <OpenApiImportModal
      open={importOpen}
      repositories={repositories}
      defaultSoftwareRepositoryId={draft.softwareRepositoryId}
      onClose={() => setImportOpen(false)}
      onImported={() => {
        setImportOpen(false)
        queryClient.invalidateQueries({ queryKey: ['apiInterfaces'] })
        queryClient.invalidateQueries({ queryKey: ['softwareRepositories', projectId] })
        if (isCreate) {
          const target = draft.softwareRepositoryId
            ? `?tab=interfaces&softwareRepositoryId=${encodeURIComponent(draft.softwareRepositoryId)}`
            : '?tab=interfaces'
          navigate(`/asset-library${target}`)
          return
        }
        if (interfaceId) void interfaceQuery.refetch()
      }}
    />
  )
}
