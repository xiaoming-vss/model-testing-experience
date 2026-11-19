import { Alert } from 'antd'
import { ApiCaseExplorer } from './ApiCaseExplorer'
import { ApiCaseEditorPanel } from './ApiCaseEditorPanel'
import { ApiCollectionToolbar } from './ApiCollectionToolbar'
import { getErrorMessage } from '@/utils/format'
import type { ApiCollectionDetailPageModel } from '../hooks/useApiCollectionDetailPage'

export function ApiCollectionWorkspace({ page }: { page: ApiCollectionDetailPageModel }) {
  const {
    collectionQuery,
    casesQuery,
    selectedCaseDetailQuery,
    requirementQuery,
    sprintQuery,
    assertRulesQuery,
    extractRulesQuery,
    requirementId,
    sprintId,
    cases,
    selectedEnvironment,
    collectionRunHistoryTotal,
    runApiCollectionMutation,
    resolvedEnvironmentId,
    onBack,
    setCollectionRunHistoryOpen,
    handleRunCollection,
    sidebarCases,
    selectedCaseId,
    setSelectedCaseId,
    caseSearch,
    setCaseSearch,
    canReorder,
    draggingCaseId,
    openCreateDrawer,
    openCaseImportModal,
    handleDeleteCase,
    handleDiscardDraft,
    handleCaseDragStart,
    handleCaseDrop,
    handleCaseDragEnd,
    updatedAtText,
  } = page

  const queryErrors = [
    collectionQuery.error,
    casesQuery.error,
    selectedCaseDetailQuery.error,
    requirementQuery.error,
    sprintQuery.error,
    assertRulesQuery.error,
    extractRulesQuery.error,
  ]

  return (
    <div className="api-automation-content">
      <div className="w-full api-collection-workbench tp-board min-h-0 flex-auto">
        {queryErrors.map((error, index) => error ? (
          <Alert key={index} showIcon type="error" title={getErrorMessage(error)} />
        ) : null)}

        <ApiCollectionToolbar
          collectionName={collectionQuery.data?.name ?? '-'}
          requirementName={requirementQuery.data?.name ?? requirementId ?? '-'}
          sprintName={sprintQuery.data?.name ?? sprintId ?? '-'}
          updatedAt={updatedAtText}
          environmentBaseUrl={selectedEnvironment?.baseUrl ?? ''}
          runHistoryCount={collectionRunHistoryTotal}
          runningCollection={runApiCollectionMutation.isPending}
          runDisabled={!resolvedEnvironmentId || cases.length === 0}
          onBack={onBack}
          onOpenRunHistory={() => setCollectionRunHistoryOpen(true)}
          onRunCollection={handleRunCollection}
        />

        <div className="api-wb-cols grid min-h-0 flex-auto grid-cols-[var(--app-sidebar-width)_minmax(0,1fr)] items-stretch gap-3 max-[1180.01px]:grid-cols-1 max-[1180.01px]:grid-rows-[minmax(180px,460px)_minmax(400px,1fr)] max-[1180.01px]:overflow-y-auto">
          <ApiCaseExplorer
            cases={sidebarCases}
            selectedCaseId={selectedCaseId}
            loading={casesQuery.isLoading}
            totalCaseCount={cases.length}
            search={caseSearch}
            canReorder={canReorder}
            draggingCaseId={draggingCaseId}
            onSearchChange={setCaseSearch}
            onSelectCase={setSelectedCaseId}
            onCreateCase={openCreateDrawer}
            onImportCases={openCaseImportModal}
            onDeleteCase={handleDeleteCase}
            onDiscardDraft={handleDiscardDraft}
            onDragStart={handleCaseDragStart}
            onDrop={handleCaseDrop}
            onDragEnd={handleCaseDragEnd}
          />

          <ApiCaseEditorPanel page={page} />
        </div>
      </div>
    </div>
  )
}
