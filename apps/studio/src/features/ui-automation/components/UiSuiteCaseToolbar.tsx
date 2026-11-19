import { goBackOrFallback } from '@/shared/utils/backNavigation'
import { UiSuiteDetailToolbar } from './UiSuiteDetailToolbar'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiSuiteCaseToolbar({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    navigate,
    suiteId,
    suiteQuery,
    requirementQuery,
    requirementId,
    sprintQuery,
    sprintId,
    readiness,
    lastRunText,
    suiteRunHistoryTotal,
    runSuiteMutation,
    debugRunMutation,
    createCaseMutation,
    updateCaseMutation,
    reorderCasesMutation,
    uiTestCases,
    resolvedEnvironmentId,
    activeCaseId,
    isCreatingCase,
    flowLevel,
    showEditorForm,
    orderedCases,
    canReorder,
    can,
    environmentOptions,
    environmentsQuery,
    caseSerial,
    editingCase,
    draftCase,
    watchedSteps,
    watchedEnabled,
    caseDirty,
    setSelectedEnvironmentId,
    setEnvironmentDrawerOpen,
    setFlowLevel,
    setSuiteRunHistoryOpen,
    handleDebugRun,
    handleRunSuite,
    handleCaseSave,
    openCaseImportModal,
  } = page

  return <UiSuiteDetailToolbar
    suiteName={suiteQuery.data?.name || '-'}
    requirementName={requirementQuery.data?.name ?? requirementId ?? '-'}
    sprintName={sprintQuery.data?.name ?? sprintId ?? '-'}
    readiness={readiness}
    lastRunText={lastRunText}
    runHistoryCount={suiteRunHistoryTotal}
    runningSuite={runSuiteMutation.isPending}
    debugging={debugRunMutation.isPending}
    saving={createCaseMutation.isPending || updateCaseMutation.isPending || reorderCasesMutation.isPending}
    canRun={Boolean(suiteId) && uiTestCases.length > 0 && Boolean(resolvedEnvironmentId) && !reorderCasesMutation.isPending}
    canDebug={Boolean(activeCaseId) && !isCreatingCase && Boolean(resolvedEnvironmentId)}
    showDebug={flowLevel === 'steps' && showEditorForm}
    showSuiteActions={flowLevel === 'cases'}
    canSave={flowLevel === 'cases' && orderedCases.length > 0 ? canReorder && !reorderCasesMutation.isPending : showEditorForm}
    importDisabled={!suiteId || !can('write')}
    environmentId={resolvedEnvironmentId}
    environmentOptions={environmentOptions}
    environmentsLoading={environmentsQuery.isLoading}
    showCase={flowLevel === 'steps'}
    caseEditable={flowLevel === 'steps' && showEditorForm}
    caseSerial={caseSerial}
    caseName={editingCase?.name || draftCase?.name || ''}
    caseStepCount={watchedSteps.length}
    caseEnabled={Boolean(watchedEnabled)}
    saveDirty={flowLevel === 'steps' && caseDirty}
    onEnvironmentChange={setSelectedEnvironmentId}
    onOpenEnvironments={() => setEnvironmentDrawerOpen(true)}
    onBack={() => goBackOrFallback(navigate, '/testing?tab=ui')}
    onOpenSuiteFlow={() => setFlowLevel('cases')}
    onOpenRunHistory={() => setSuiteRunHistoryOpen(true)}
    onDebugRun={handleDebugRun}
    onRunSuite={handleRunSuite}
    onSave={handleCaseSave}
    onImport={openCaseImportModal}
  />
}
