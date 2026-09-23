import type { UiTestCaseRun } from '@/services/api'
import { useEffect, useMemo, useState } from 'react'

import { buildUiStepSnapshots } from '../utils/detailRunView'
import { UiRunConsoleCard } from './UiRunConsoleCard'
import { UiRunReplayStage } from './UiRunReplayStage'
import { UiRunSnapshotStrip } from './UiRunSnapshotStrip'

/*
 * 详情页右栏：执行回放 + 关键帧快照 + 执行控制台，三张卡片恒定显示。
 * 当前回放到第几步由这里持有，换运行记录时回到第一步。
 */

type Props = {
  run: UiTestCaseRun | null
  viewportText: string
  screenshotText: string
  refreshing: boolean
  onRefreshRun: () => void
}

export function UiRunInspector({ run, viewportText, screenshotText, refreshing, onRefreshRun }: Props) {
  const [activeIndex, setActiveIndex] = useState(0)
  const snapshots = useMemo(() => buildUiStepSnapshots(run?.stepResults ?? []), [run?.stepResults])
  const runKey = run?.runId ?? run?.uiTestCaseRunId ?? ''

  useEffect(() => {
    setActiveIndex(0)
  }, [runKey])

  // 步骤结果随轮询增长时，索引可能越界；夹到最后一帧而不是清空当前选择。
  const safeIndex = snapshots.length === 0 ? 0 : Math.min(activeIndex, snapshots.length - 1)

  return (
    <div className="ui-wb-inspector">
      <div className="ui-wb-inspector-slot">
        <UiRunReplayStage
          run={run}
          snapshots={snapshots}
          activeIndex={safeIndex}
          viewportText={viewportText}
          screenshotText={screenshotText}
          onActiveIndexChange={setActiveIndex}
        />
      </div>

      <div className="ui-wb-inspector-slot">
        <UiRunSnapshotStrip snapshots={snapshots} activeIndex={safeIndex} onSelect={setActiveIndex} />
      </div>

      <div className="ui-wb-inspector-slot">
        <UiRunConsoleCard run={run} refreshing={refreshing} onRefresh={onRefreshRun} />
      </div>
    </div>
  )
}
