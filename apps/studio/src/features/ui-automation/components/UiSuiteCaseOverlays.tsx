import { CaseImportModal } from '@/domain/projects/components/CaseImportModal'
import { DynamicValuePickerModal } from '@/domain/projects/components/DynamicValuePickerModal'
import { EnvironmentDrawer } from '@/domain/projects/components/EnvironmentDrawer'
import { uiBuiltinTemplateFunctions } from '@/shared/constants/templateFunctions'
import { UI_TEMPLATE_FIELD_LABELS } from '../utils/detailView'
import { UiMissingVariablesModal } from './UiMissingVariablesModal'
import { UiSuiteRunHistory } from './UiSuiteRunHistory'
import { UiSuiteRunReport } from './UiSuiteRunReport'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiSuiteCaseOverlays({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    caseImportModalOpen,
    closeCaseImportModal,
    handleImportUiCases,
    importUiCasesMutation,
    caseImportMode,
    setCaseImportMode,
    setImportYamlFile,
    importYamlText,
    setImportYamlText,
    suiteRunHistoryOpen,
    setSuiteRunHistoryOpen,
    suiteRunHistoryQuery,
    suiteRunHistory,
    suiteRunHistoryTotal,
    loadingSuiteRunHistoryId,
    handleOpenSuiteRunHistoryItem,
    can,
    suiteRunReportOpen,
    closeSuiteRunReport,
    suiteRunReportQuery,
    suiteRunReport,
    handleRefreshSuiteRunReport,
    refreshingSuiteRunReport,
    selectedSuiteRunId,
    suiteRunReportView,
    setSuiteRunReportView,
    orderedSuiteRunItems,
    selectedSuiteRunSummary,
    expandedSuiteRunItemIds,
    toggleSuiteRunItem,
    environmentDrawerOpen,
    projectId,
    resolvedEnvironmentId,
    setEnvironmentDrawerOpen,
    setSelectedEnvironmentId,
    templatePickerTarget,
    pickerEnvironmentVars,
    environmentVarsQuery,
    formatEnvironmentTokenForTarget,
    insertTemplateToken,
    setTemplatePickerTarget,
  } = page

  return <>
    <CaseImportModal
      open={caseImportModalOpen}
      onClose={closeCaseImportModal}
      onConfirm={handleImportUiCases}
      confirmLoading={importUiCasesMutation.isPending}
      importMode={caseImportMode}
      onImportModeChange={setCaseImportMode}
      onFileChange={setImportYamlFile}
      yamlText={importYamlText}
      onYamlTextChange={setImportYamlText}
      targetLabel="UI 测试集"
    />

    <UiSuiteRunHistory suiteRunHistoryOpen={suiteRunHistoryOpen} setSuiteRunHistoryOpen={setSuiteRunHistoryOpen} suiteRunHistoryQuery={suiteRunHistoryQuery} suiteRunHistory={suiteRunHistory} suiteRunHistoryTotal={suiteRunHistoryTotal} loadingSuiteRunHistoryId={loadingSuiteRunHistoryId} handleOpenSuiteRunHistoryItem={handleOpenSuiteRunHistoryItem} />

    <UiSuiteRunReport canStop={can('execute')} suiteRunReportOpen={suiteRunReportOpen} closeSuiteRunReport={closeSuiteRunReport} suiteRunReportQuery={suiteRunReportQuery} suiteRunReport={suiteRunReport} handleRefreshSuiteRunReport={handleRefreshSuiteRunReport} refreshingSuiteRunReport={refreshingSuiteRunReport} selectedSuiteRunId={selectedSuiteRunId} suiteRunReportView={suiteRunReportView} setSuiteRunReportView={setSuiteRunReportView} orderedSuiteRunItems={orderedSuiteRunItems} selectedSuiteRunSummary={selectedSuiteRunSummary} expandedSuiteRunItemIds={expandedSuiteRunItemIds} toggleSuiteRunItem={toggleSuiteRunItem} />

    <EnvironmentDrawer
      open={environmentDrawerOpen}
      projectId={projectId}
      kind="ui"
      currentEnvironmentId={resolvedEnvironmentId}
      onClose={() => setEnvironmentDrawerOpen(false)}
      onSelectEnvironment={(environmentId) => setSelectedEnvironmentId(environmentId ?? '')}
    />

    <DynamicValuePickerModal
      open={Boolean(templatePickerTarget)}
      environmentVars={pickerEnvironmentVars}
      hasEnvironment={Boolean(resolvedEnvironmentId)}
      environmentLoading={environmentVarsQuery.isLoading}
      builtinFunctions={uiBuiltinTemplateFunctions}
      formatVariableToken={formatEnvironmentTokenForTarget}
      targetLabel={
        templatePickerTarget ? UI_TEMPLATE_FIELD_LABELS[templatePickerTarget.fieldKey] : undefined
      }
      onInsert={(token) => {
        if (!templatePickerTarget) return
        insertTemplateToken(templatePickerTarget.stepIndex, templatePickerTarget.fieldKey, token)
      }}
      onClose={() => setTemplatePickerTarget(null)}
    />

    <UiMissingVariablesModal page={page} />
  </>
}
