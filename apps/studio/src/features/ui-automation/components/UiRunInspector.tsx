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
    <div className={`ui-wb-inspector ui-wb-inspector-unified ui-wb-inspector-stacked${showStepConfig ? ' has-step-config' : ''}`}>
      <div className="ui-inspector-run">
        <div className="ui-inspector-tabs" role="tablist" aria-label="运行结果">
          {([['replay', '执行回放'], ['logs', '执行日志'], ['variables', '运行变量']] as const).map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeTab === key} onClick={() => setActiveTab(key)}>{label}</button>)}
        </div>
        <div className="ui-inspector-tab-content" hidden={activeTab !== 'replay'}>
          <UiRunReplayStage run={run} snapshots={snapshots} activeIndex={safeIndex} viewportText={viewportText} viewportWidth={viewportWidth} viewportHeight={viewportHeight} screenshotText={screenshotText} onActiveIndexChange={setActiveIndex} />
        </div>
        <div className="ui-inspector-tab-content" hidden={activeTab !== 'logs'}>
          <UiRunConsoleCard run={run} refreshing={refreshing} onRefresh={onRefreshRun} canStop={canStop} />
        </div>
        <div className="ui-inspector-tab-content" hidden={activeTab !== 'variables'}><UiRunVariables run={run} /></div>
      </div>
      <div className="ui-inspector-step-host" hidden={!showStepConfig} ref={stepConfigHostRef} />
    </div>
  )
}
