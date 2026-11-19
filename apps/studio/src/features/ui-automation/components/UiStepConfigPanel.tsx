import { Form, Switch } from 'antd'
import { createPortal } from 'react-dom'
import { UiStepResultBadge } from './UiStepResultBadge'
import { UiStepEditor } from './UiStepEditor'
import { LeftOutlined, RightOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import type { UiTestSuiteCasePageModel } from '../hooks/useUiTestSuiteCasePage'

export function UiStepConfigPanel({ page }: { page: UiTestSuiteCasePageModel }) {
  const {
    stepConfigHost,
    watchedSteps,
    selectedStepIndex,
    setSelectedStepIndex,
    setExpandedStepIndexes,
    currentRunStepResults,
    stepConfigTab,
    setStepConfigTab,
    expandedStepIndexes,
    draggingStepIndex,
    handleStepDrop,
    can,
    handleStepDragStart,
    setDraggingStepIndex,
    toggleStepPanel,
    removeStep,
    renderTemplatePickerLabel,
    bindTemplateInputRef,
  } = page

  if (!stepConfigHost) return null

  const stepConfigActions = (
    <div className="ui-wb-pipeline-actions mb-4 flex flex-wrap items-center justify-between gap-1.5">
      <div className="ui-step-header-switches mr-auto flex flex-wrap items-center gap-5">
        <label className="flex items-center gap-1.5 whitespace-nowrap text-xs text-[var(--srf-text-secondary)]"><Form.Item name={[selectedStepIndex, 'enabled']} valuePropName="checked" noStyle><Switch size="small" aria-label="启用步骤" disabled={!can('write')} /></Form.Item>启用</label>
        <label className="flex items-center gap-1.5 whitespace-nowrap text-xs text-[var(--srf-text-secondary)]"><Form.Item name={[selectedStepIndex, 'continueOnFailure']} valuePropName="checked" noStyle><Switch size="small" aria-label="失败后继续" disabled={!can('write')} /></Form.Item>失败后继续</label>
      </div>
    </div>
  )

  return createPortal(<div className="ui-wb-pipeline flex min-h-0 min-w-0 flex-1 flex-col gap-0 overflow-hidden border-0 bg-[var(--srf-card)] p-4 px-5">
    <div className="ui-wb-pipeline-head mb-4 flex flex-wrap items-center justify-between gap-2">
      <div className="ui-wb-pipeline-title inline-flex items-center gap-2 text-[15px] font-bold text-[var(--srf-text)]">
        步骤配置
        {watchedSteps.length > 0 ? <span className="ui-wb-pipeline-chip rounded-full bg-[var(--srf-hover)] px-2 py-0.5 font-[inherit] text-[11px] font-medium leading-4 text-[var(--srf-text-muted)]">#{selectedStepIndex + 1} / {watchedSteps.length}</span> : null}
        {currentRunStepResults.find((result) => result.orderNo === selectedStepIndex + 1) ? <UiStepResultBadge stepResult={currentRunStepResults.find((result) => result.orderNo === selectedStepIndex + 1)!} /> : null}
      </div>
      <div className="ui-step-navigation-actions ml-auto flex items-center gap-1">
        <Button size="small" className="text-xs" aria-label="上一个步骤" icon={<LeftOutlined />} disabled={selectedStepIndex <= 0} onClick={() => { const index = selectedStepIndex - 1; setSelectedStepIndex(index); setExpandedStepIndexes([index]) }} />
        <Button size="small" className="text-xs" aria-label="下一个步骤" icon={<RightOutlined />} disabled={selectedStepIndex >= watchedSteps.length - 1} onClick={() => { const index = selectedStepIndex + 1; setSelectedStepIndex(index); setExpandedStepIndexes([index]) }} />
      </div>
    </div>
    <div id="ui-step-config-body" className="ui-step-details-body flex min-h-0 flex-1 flex-col gap-3 overflow-hidden">
      <UiStepEditor
        watchedSteps={watchedSteps}
        selectedStepIndex={selectedStepIndex}
        activeTab={stepConfigTab}
        onTabChange={setStepConfigTab}
        detailActions={stepConfigActions}
        expandedStepIndexes={expandedStepIndexes}
        draggingStepIndex={draggingStepIndex}
        handleStepDrop={handleStepDrop}
        can={can}
        handleStepDragStart={handleStepDragStart}
        setDraggingStepIndex={setDraggingStepIndex}
        toggleStepPanel={toggleStepPanel}
        removeStep={removeStep}
        renderTemplatePickerLabel={renderTemplatePickerLabel}
        bindTemplateInputRef={bindTemplateInputRef}
        stepResults={currentRunStepResults}
      />
    </div>
  </div>, stepConfigHost)
}
