import type { UiTestCaseRun } from '@/services/api'
import { useEffect, useMemo, useState } from 'react'

import { buildUiStepSnapshots } from '../utils/detailRunView'
import { UiRunConsoleCard } from './UiRunConsoleCard'
import { UiRunReplayStage } from './UiRunReplayStage'
import { UiRunVariables } from './UiRunVariables'

/*
 * 详情页右栏：执行回放、关键帧快照和控制台共用一个面板。
 * 当前回放到第几步由这里持有，换运行记录时回到第一步。
 */

type Props = {
  run: UiTestCaseRun | null
  viewportText: string
  viewportWidth?: number
  viewportHeight?: number
  screenshotText: string
  refreshing: boolean
  onRefreshRun: () => void
  canStop?: boolean
  showStepConfig?: boolean
  stepConfigHostRef?: (node: HTMLDivElement | null) => void
}

export function UiRunInspector({ run, viewportText, viewportWidth, viewportHeight, screenshotText, refreshing, onRefreshRun, canStop, showStepConfig, stepConfigHostRef }: Props) {
  const [activeIndex, setActiveIndex] = useState(0)
  const [activeTab, setActiveTab] = useState<'replay' | 'logs' | 'variables'>('replay')
  const snapshots = useMemo(() => buildUiStepSnapshots(run?.stepResults ?? []), [run?.stepResults])
  const runKey = run?.runId ?? run?.uiTestCaseRunId ?? ''

  useEffect(() => {
    setActiveIndex(0)
  }, [runKey])

  // 步骤结果随轮询增长时，索引可能越界；夹到最后一帧而不是清空当前选择。
  const safeIndex = snapshots.length === 0 ? 0 : Math.min(activeIndex, snapshots.length - 1)

  return (
    <div className={`ui-wb-inspector ui-wb-inspector-unified ui-wb-inspector-stacked flex min-h-0 min-w-0 flex-col rounded-[var(--srf-radius-card)] border border-[var(--srf-card-border)] bg-[var(--srf-card)]${showStepConfig ? ' has-step-config gap-0 overflow-hidden p-0 max-[1099px]:min-h-[500px]' : ' gap-3 overflow-y-auto p-3'}`}>
      <div className={`ui-inspector-run flex flex-col overflow-hidden${showStepConfig ? ' flex-[0_0_55%] min-h-[240px]' : ' flex-[1_1_52%] min-h-[180px]'}`}>
        <div className="ui-inspector-tabs flex flex-none gap-5 overflow-x-auto border-b border-[var(--srf-card-border)] px-5" role="tablist" aria-label="运行结果">
          {([['replay', '执行回放'], ['logs', '执行日志'], ['variables', '运行变量']] as const).map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeTab === key} className={`flex-none cursor-pointer border-0 border-b-2 border-transparent bg-transparent px-0 py-3 text-[var(--srf-text-secondary)]${activeTab === key ? ' border-b-[var(--srf-accent)] font-semibold text-[var(--srf-accent)]' : ''}`} onClick={() => setActiveTab(key)}>{label}</button>)}
        </div>
        <div className="ui-inspector-tab-content min-h-0 flex-1 overflow-auto p-4 px-5" hidden={activeTab !== 'replay'}>
          <UiRunReplayStage run={run} snapshots={snapshots} activeIndex={safeIndex} viewportText={viewportText} viewportWidth={viewportWidth} viewportHeight={viewportHeight} screenshotText={screenshotText} onActiveIndexChange={setActiveIndex} />
        </div>
        <div className="ui-inspector-tab-content min-h-0 flex-1 overflow-auto p-4 px-5" hidden={activeTab !== 'logs'}>
          <UiRunConsoleCard run={run} refreshing={refreshing} onRefresh={onRefreshRun} canStop={canStop} />
        </div>
        <div className="ui-inspector-tab-content min-h-0 flex-1 overflow-auto p-4 px-5" hidden={activeTab !== 'variables'}><UiRunVariables run={run} /></div>
      </div>
      <div className="ui-inspector-step-host flex min-h-[220px] flex-1 overflow-hidden border-t border-[var(--srf-card-border)]" hidden={!showStepConfig} ref={stepConfigHostRef} />
    </div>
  )
}
