import { ApiCaseEditor } from './ApiCaseEditor'
import { ApiCaseRunConsole } from './ApiCaseRunConsole'
import type { ApiCollectionDetailPageModel } from '../hooks/useApiCollectionDetailPage'

export function ApiCaseEditorPanel({ page }: { page: ApiCollectionDetailPageModel }) {
  const {
    runResult,
    editorTopHeight,
    isResizingEditor,
    editorLayoutRef,
    handleEditorSplitterPointerDown,
    caseForm,
    isCreatingCase,
    setDraftCaseValues,
    getCompleteCaseFormValues,
    createCaseMutation,
    editingCase,
    activeCaseId,
    updateCaseMutation,
    pathInputRef,
    runApiCaseMutation,
    isApiCaseRunInProgress,
    isSelectedCaseReady,
    handleSendRequest,
    ensureQueryTrailingRow,
    environmentPopoverOpen,
    setEnvironmentPopoverOpen,
    environments,
    resolvedEnvironmentId,
    handleSelectEnvironment,
    switchDefaultEnvironmentMutation,
    projectId,
    selectedEnvironment,
    environmentsQuery,
    setEnvVarInputRef,
    renderEnvVarPicker,
    insertTemplateText,
    bodyJsonEditorRef,
    insertTemplateTextIntoJson,
    handleFormatBodyJson,
    handleCompressBodyJson,
    postOperationCount,
    can,
    openCreateAssertRule,
    openCreateExtractRule,
    assertRulesQuery,
    extractRulesQuery,
    assertRules,
    toggleAssertRuleMutation,
    openEditAssertRule,
    deleteAssertRuleMutation,
    extractRules,
    toggleExtractRuleMutation,
    openEditExtractRule,
    deleteExtractRuleMutation,
    runResultView,
    setRunResultView,
  } = page

  return (
    <section className="api-wb-editor-panel flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[12px] border border-[var(--srf-card-border)] bg-[var(--srf-card)]">
      <div className="api-wb-editor-shell flex min-h-0 flex-auto flex-col" ref={editorLayoutRef}>
        <div className="api-wb-editor-main flex min-h-0 flex-auto flex-col" style={runResult ? { flexBasis: `${editorTopHeight}px` } : undefined}>
          <div className="api-wb-editor-main-scroll min-h-0 flex-auto overflow-auto [container-type:size]">
            <ApiCaseEditor caseForm={caseForm} isCreatingCase={isCreatingCase} setDraftCaseValues={setDraftCaseValues} getCompleteCaseFormValues={getCompleteCaseFormValues} createCaseMutation={createCaseMutation} editingCase={editingCase} activeCaseId={activeCaseId} updateCaseMutation={updateCaseMutation} pathInputRef={pathInputRef} runApiCaseMutation={runApiCaseMutation} isApiCaseRunInProgress={isApiCaseRunInProgress} isSelectedCaseReady={isSelectedCaseReady} handleSendRequest={handleSendRequest} ensureQueryTrailingRow={ensureQueryTrailingRow} environment={{ environmentPopoverOpen, setEnvironmentPopoverOpen, environments, resolvedEnvironmentId, handleSelectEnvironment, switchDefaultEnvironmentMutation, projectId, selectedEnvironment, environmentsQuery }} templates={{ setEnvVarInputRef, renderEnvVarPicker, insertTemplateText, bodyJsonEditorRef, insertTemplateTextIntoJson, handleFormatBodyJson, handleCompressBodyJson }} rules={{ postOperationCount, can, openCreateAssertRule, openCreateExtractRule, assertRulesQuery, extractRulesQuery, assertRules, toggleAssertRuleMutation, openEditAssertRule, deleteAssertRuleMutation, extractRules, toggleExtractRuleMutation, openEditExtractRule, deleteExtractRuleMutation }} />
          </div>
        </div>
        {runResult ? (
          <>
            <div
              className={`api-wb-splitter group flex h-3 flex-none cursor-row-resize items-center gap-1.5 border-y border-[var(--srf-divider)] bg-[var(--srf-card)] px-4${isResizingEditor ? ' resizing' : ''}`}
              role="separator"
              aria-orientation="horizontal"
              aria-label="调整请求编辑区与运行结果的高度"
              onPointerDown={handleEditorSplitterPointerDown}
            >
              <span className={`api-wb-splitter-line h-px flex-auto ${isResizingEditor ? 'bg-[var(--srf-accent)]' : 'bg-[var(--srf-card-border)] group-hover:bg-[var(--srf-accent)]'}`} />
              <span className="api-wb-splitter-grip text-[10px] leading-none text-[var(--srf-text-muted)]">⋯</span>
            </div>
            <div className="api-wb-console-pane flex min-h-0 flex-auto flex-col">
              <div className="api-wb-console-scroll min-h-0 flex-auto overflow-hidden">
                <ApiCaseRunConsole
                  result={runResult}
                  canStop={can('execute')}
                  environmentName={selectedEnvironment?.name ?? runResult.environmentId ?? '-'}
                  view={runResultView}
                  onViewChange={(value) => setRunResultView(value)}
                />
              </div>
            </div>
          </>
        ) : null}
      </div>
    </section>
  )
}
