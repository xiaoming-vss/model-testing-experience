import { CaseImportModal } from '@/domain/projects/components/CaseImportModal'
import { ApiAssertRuleEditor } from './ApiAssertRuleEditor'
import { ApiCollectionRunHistory } from './ApiCollectionRunHistory'
import { ApiCollectionRunReportModal } from './ApiCollectionRunReport'
import { ApiEnvVarPickerModal } from './ApiEnvVarPickerModal'
import { ApiExtractRuleEditor } from './ApiExtractRuleEditor'
import type { ApiCollectionDetailPageModel } from '../hooks/useApiCollectionDetailPage'

export function ApiCollectionOverlays({ page }: { page: ApiCollectionDetailPageModel }) {
  const {
    caseImportModalOpen,
    closeCaseImportModal,
    handleImportApiCases,
    importApiCasesMutation,
    caseImportMode,
    setCaseImportMode,
    setImportYamlFile,
    importYamlText,
    setImportYamlText,
    collectionRunHistoryOpen,
    setCollectionRunHistoryOpen,
    collectionRunHistoryQuery,
    collectionRunHistory,
    collectionRunHistoryTotal,
    loadingCollectionRunHistoryId,
    environments,
    handleOpenCollectionRunHistoryItem,
    can,
    collectionRunReportOpen,
    setCollectionRunReportOpen,
    setSelectedCollectionRunId,
    collectionRunReportQuery,
    collectionRunReport,
    handleExportCollectionRunReportHtml,
    handleRefreshCollectionRunReport,
    refreshingCollectionRunReport,
    selectedCollectionRunId,
    collectionRunReportView,
    setCollectionRunReportView,
    orderedCollectionRunItems,
    expandedCollectionRunItemIds,
    collectionRunItemViews,
    toggleCollectionRunItem,
    handleCollectionRunItemViewChange,
    selectedCollectionRunSummary,
    assertRuleModalOpen,
    editingAssertRule,
    setAssertRuleModalOpen,
    setEditingAssertRule,
    assertRuleForm,
    saveAssertRuleMutation,
    watchedAssertSource,
    watchedAssertComparator,
    extractRuleModalOpen,
    editingExtractRule,
    setExtractRuleModalOpen,
    setEditingExtractRule,
    extractRuleForm,
    saveExtractRuleMutation,
    watchedExtractSource,
    envVarPicker,
  } = page

  return (
    <>
      <CaseImportModal
        open={caseImportModalOpen}
        onClose={closeCaseImportModal}
        onConfirm={handleImportApiCases}
        confirmLoading={importApiCasesMutation.isPending}
        importMode={caseImportMode}
        onImportModeChange={setCaseImportMode}
        onFileChange={setImportYamlFile}
        yamlText={importYamlText}
        onYamlTextChange={setImportYamlText}
        targetLabel="Collection"
      />

      <ApiCollectionRunHistory collectionRunHistoryOpen={collectionRunHistoryOpen} setCollectionRunHistoryOpen={setCollectionRunHistoryOpen} collectionRunHistoryQuery={collectionRunHistoryQuery} collectionRunHistory={collectionRunHistory} collectionRunHistoryTotal={collectionRunHistoryTotal} loadingCollectionRunHistoryId={loadingCollectionRunHistoryId} environments={environments} handleOpenCollectionRunHistoryItem={handleOpenCollectionRunHistoryItem} />

      <ApiCollectionRunReportModal canStop={can('execute')} collectionRunReportOpen={collectionRunReportOpen} setCollectionRunReportOpen={setCollectionRunReportOpen} setSelectedCollectionRunId={setSelectedCollectionRunId} collectionRunReportQuery={collectionRunReportQuery} collectionRunReport={collectionRunReport} environments={environments} handleExportCollectionRunReportHtml={handleExportCollectionRunReportHtml} handleRefreshCollectionRunReport={handleRefreshCollectionRunReport} refreshingCollectionRunReport={refreshingCollectionRunReport} selectedCollectionRunId={selectedCollectionRunId} collectionRunReportView={collectionRunReportView} setCollectionRunReportView={setCollectionRunReportView} orderedCollectionRunItems={orderedCollectionRunItems} expandedCollectionRunItemIds={expandedCollectionRunItemIds} collectionRunItemViews={collectionRunItemViews} toggleCollectionRunItem={toggleCollectionRunItem} handleCollectionRunItemViewChange={handleCollectionRunItemViewChange} selectedCollectionRunSummary={selectedCollectionRunSummary} />

      <ApiAssertRuleEditor assertRuleModalOpen={assertRuleModalOpen} editingAssertRule={editingAssertRule} setAssertRuleModalOpen={setAssertRuleModalOpen} setEditingAssertRule={setEditingAssertRule} assertRuleForm={assertRuleForm} saveAssertRuleMutation={saveAssertRuleMutation} watchedAssertSource={watchedAssertSource} watchedAssertComparator={watchedAssertComparator} />

      <ApiExtractRuleEditor extractRuleModalOpen={extractRuleModalOpen} editingExtractRule={editingExtractRule} setExtractRuleModalOpen={setExtractRuleModalOpen} setEditingExtractRule={setEditingExtractRule} extractRuleForm={extractRuleForm} saveExtractRuleMutation={saveExtractRuleMutation} watchedExtractSource={watchedExtractSource} />

      <ApiEnvVarPickerModal picker={envVarPicker} />
    </>
  )
}
