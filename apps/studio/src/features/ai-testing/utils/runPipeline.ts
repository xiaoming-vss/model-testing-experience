import { runStatusMeta } from '@/domain/runs/status'

export type RunPipelineTone = 'processing' | 'success' | 'error' | 'muted'

export type RunPipelineModel = {
  statusLabel: string
  statusTone: RunPipelineTone
}

/** 运行列表只展示一个状态标签；阶段进度由生成链自己的阶段视图表达。 */
export function getRunPipelineModel(run: { status?: string }): RunPipelineModel {
  const meta = runStatusMeta(run.status)
  if (meta.value === 'unknown') return { statusLabel: '成功', statusTone: 'success' }
  return { statusLabel: meta.label, statusTone: meta.tone }
}
