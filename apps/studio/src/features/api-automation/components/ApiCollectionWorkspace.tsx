import { Alert } from 'antd'
import { ApiCaseExplorer } from './ApiCaseExplorer'
import { ApiCaseEditorPanel } from './ApiCaseEditorPanel'
import { ApiCollectionToolbar } from './ApiCollectionToolbar'
import { CaseInvalidationModal } from '@/shared/components/CaseInvalidationModal'
import { isCaseInvalidated } from '@/shared/utils/caseInvalidation'
import { getErrorMessage } from '@/utils/format'
import { getCaseId } from '../utils/apiCaseEditor'
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
    invalidatedFilter,
    setInvalidatedFilter,
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
    caseStatusOpen,
    setCaseStatusOpen,
    batchInvalidateCasesMutation,
    can,
    projectId,
  } = page

  const invalidatedCount = cases.filter((item) => isCaseInvalidated(item)).length
  const runnableCount = cases.length - invalidatedCount

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
          requirementName={requirementQuery.data?.name ?? requirementId ?? '项目级'}
          sprintName={sprintQuery.data?.name ?? sprintId ?? ''}
          updatedAt={updatedAtText}
          environmentName={selectedEnvironment?.name ?? ''}
          environmentBaseUrl={selectedEnvironment?.baseUrl ?? ''}
          runHistoryCount={collectionRunHistoryTotal}
          runningCollection={runApiCollectionMutation.isPending}
          runDisabled={!resolvedEnvironmentId || runnableCount === 0}
          canManageCases={can('write') && Boolean(projectId)}
          invalidatedCount={invalidatedCount}
          onBack={onBack}
          onOpenRunHistory={() => setCollectionRunHistoryOpen(true)}
          onRunCollection={handleRunCollection}
          onOpenCaseStatus={() => setCaseStatusOpen(true)}
        />

        <div className="api-wb-cols grid min-h-0 flex-auto grid-cols-[var(--app-sidebar-width)_minmax(0,1fr)] items-stretch gap-3 max-[1180.01px]:grid-cols-1 max-[1180.01px]:grid-rows-[minmax(180px,460px)_minmax(400px,1fr)] max-[1180.01px]:overflow-y-auto">
          <ApiCaseExplorer
            cases={sidebarCases}
            selectedCaseId={selectedCaseId}
            loading={casesQuery.isLoading}
            totalCaseCount={cases.length}
            validCaseCount={cases.length - invalidatedCount}
            invalidCaseCount={invalidatedCount}
            search={caseSearch}
            invalidatedFilter={invalidatedFilter}
            onInvalidatedFilterChange={setInvalidatedFilter}
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

      <CaseInvalidationModal
        open={caseStatusOpen}
        scopeLabel={`${collectionQuery.data?.name ?? '当前 Collection'} · ${cases.length} 条用例`}
        cases={cases.map((item) => ({
          id: getCaseId(item),
          name: item.name,
          invalidatedAt: item.invalidatedAt,
        }))}
        canWrite={can('write')}
        pending={batchInvalidateCasesMutation.isPending}
        onClose={() => setCaseStatusOpen(false)}
        onSubmit={(caseIds, invalidated) =>
          batchInvalidateCasesMutation.mutate({ caseIds, invalidated })
        }
      />
    </div>
  )
}
