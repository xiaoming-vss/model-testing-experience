export type RunPipelineTone = 'processing' | 'success' | 'error' | 'muted'

export type RunPipelineModel = {
  statusLabel: string
  statusTone: RunPipelineTone
}

const inProgressRunStatuses = ['pending', 'queued', 'claimed', 'running', 'waiting_review']

/** 运行列表只展示一个状态标签；阶段进度由生成链自己的阶段视图表达。 */
export function getRunPipelineModel(run: { status?: string }): RunPipelineModel {
  const status = (run.status ?? '').toLowerCase()
  if (status === 'failed' || status === 'error') {
    return { statusLabel: status === 'error' ? '异常' : '失败', statusTone: 'error' }
  }
  if (status === 'canceled') {
    return { statusLabel: '已取消', statusTone: 'muted' }
  }
  if (inProgressRunStatuses.includes(status)) {
    return { statusLabel: '执行中', statusTone: 'processing' }
  }
  return { statusLabel: '成功', statusTone: 'success' }
}
