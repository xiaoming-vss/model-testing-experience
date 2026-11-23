import { Empty } from 'antd'
import { ProjectActionButton } from '@/domain/projects/components/ProjectActionButton'
import { UiExecutionFlow } from './UiExecutionFlow'
import { UiFlowLoading } from './UiFlowLoading'
import { UiStepConfigPanel } from './UiStepConfigPanel'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiSuiteCaseFlowPanel({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    flowLevel,
    invalidatedFilter,
    setInvalidatedFilter,
    caseFlowRef,
    caseFlowItems,
    runningCaseIds,
    suiteId,
    canReorder,
    reorderCasesMutation,
    handleSelectCase,
    applyCaseFlowOrder,
    can,
    openCreateCase,
    caseList,
    casesQuery,
    caseDetailLoading,
    showEditorForm,
    stepFlowRef,
    stepFlowItems,
    runningStepIds,
    selectedCaseId,
    selectedStepIndex,
    setSelectedStepIndex,
    setExpandedStepIndexes,
    addStep,
    applyStepFlowOrder,
    selectedCaseDetailQuery,
  } = page

  return <div className="ui-wb-main ui-suite-case-editor-panel flex min-h-0 min-w-0 flex-col gap-3">
    {flowLevel === 'cases' ? <>
      <div className="ui-wb-case-status-filter flex flex-none flex-wrap items-center gap-2 px-1 text-[12px] text-[var(--srf-text-secondary)]">
        <span>状态:</span>
        {([
          ['all', '全部'],
          ['valid', '有效'],
          ['invalid', '已失效'],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`tp-chip${invalidatedFilter === value ? ' active' : ''}`}
            aria-pressed={invalidatedFilter === value}
            onClick={() => setInvalidatedFilter(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <UiExecutionFlow
        ref={caseFlowRef} inlineSave
        key={`cases:${suiteId}:${caseFlowItems.map((item) => item.id).join('|')}`}
        items={caseFlowItems} runningIds={runningCaseIds} storageKey={`ui-flow:${suiteId}:cases`} editable={canReorder && !reorderCasesMutation.isPending}
        applying={reorderCasesMutation.isPending} onSelect={handleSelectCase} onOpen={handleSelectCase} onApply={applyCaseFlowOrder}
        onAdd={can('write') ? openCreateCase : undefined} addLabel="添加用例" hint="点击用例进入 · "
      />
    </> : null}
    <div className="ui-flow-editor flex min-h-0 flex-1 flex-col" hidden={flowLevel === 'cases'}>
      {caseList.length === 0 ? (
        casesQuery.isLoading ? <UiFlowLoading label="正在加载 UI 测试用例..." /> : (
          <div className="ui-wb-pipeline flex flex-col gap-3 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3">
            <div className="ui-test-case-empty-editor grid min-h-[360px] place-items-center px-6 pb-6">
              <Empty description="当前测试集还没有 UI测试用例">
                <ProjectActionButton action="write" type="primary" className="action-btn-create" operation="create" onClick={openCreateCase}>
                  新建用例
                </ProjectActionButton>
              </Empty>
            </div>
          </div>
        )
      ) : caseDetailLoading ? (
        <UiFlowLoading label="正在加载 UI 测试用例详情..." />
      ) : showEditorForm ? (
        <>
          {flowLevel === 'steps' ? <UiExecutionFlow
            ref={stepFlowRef} inlineSave
            key={`steps:${suiteId}:${selectedCaseId}`}
            items={stepFlowItems} runningIds={runningStepIds} storageKey={`ui-flow:${suiteId}:steps:${selectedCaseId}`} editable={can('write')} remapPositionsOnApply
            selectedId={String(selectedStepIndex)} onApply={applyStepFlowOrder}
            onAdd={can('write') ? addStep : undefined} addLabel="添加步骤"
            onSelect={(id) => { const index = Number(id); setSelectedStepIndex(index); setExpandedStepIndexes([index]) }}
          /> : null}

          <UiStepConfigPanel page={page} />
        </>
      ) : (
        <div className="ui-wb-pipeline flex flex-col gap-3 rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)] p-3">
          <div className="ui-test-case-empty-editor grid min-h-[360px] place-items-center px-6 pb-6">
            <Empty description={selectedCaseDetailQuery.isError ? 'UI测试用例详情加载失败' : '未找到对应的 UI测试用例'} />
          </div>
        </div>
      )}
    </div>
  </div>
}
