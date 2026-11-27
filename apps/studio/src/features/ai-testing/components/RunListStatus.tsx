import type { ReactNode } from 'react'
import { getRunPipelineModel, type RunPipelineTone } from '../utils/runPipeline'

const toneClass: Record<RunPipelineTone, string> = {
  processing: 'tone-blue', success: 'tone-green', error: 'tone-red', muted: 'tone-slate',
}

/** 列表使用公共色调标签，阶段进度通过状态提示查看。 */
export function RunListStatus({ run, stageTag }: {
  run: { status?: string }
  stageTag?: ReactNode
}) {
  const model = getRunPipelineModel(run)
  return <div className="ai-task-run-list-status flex flex-wrap items-center gap-2">
    <span className={`tp-tone-tag ${toneClass[model.statusTone]}`}>{model.statusLabel}</span>
    {stageTag}
  </div>
}
