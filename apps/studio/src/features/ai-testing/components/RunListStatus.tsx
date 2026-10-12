import { Tooltip } from 'antd'
import type { ReactNode } from 'react'
import { getRunPipelineModel, type RunPipelineStageKey, type RunPipelineTone } from '../utils/runPipeline'

const toneClass: Record<RunPipelineTone, string> = {
  processing: 'tone-blue', success: 'tone-green', error: 'tone-red',
  warning: 'tone-amber', purple: 'tone-purple', muted: 'tone-slate',
}

/** 列表使用公共色调标签，各阶段进度通过状态提示查看。 */
export function RunListStatus({ run, stages, stageTag }: {
  run: { status?: string; reviewStatus?: string; importStatus?: string }
  stages?: RunPipelineStageKey[]
  stageTag?: ReactNode
}) {
  const model = getRunPipelineModel(run, { stages })
  return <div className="ai-task-run-list-status">
    <Tooltip title={model.stages.map(stage => `${stage.label}：${stage.tooltip}`).join('；')}>
      <span className={`tp-tone-tag ${toneClass[model.statusTone]}`}>{model.statusLabel}</span>
    </Tooltip>
    {stageTag}
  </div>
}
