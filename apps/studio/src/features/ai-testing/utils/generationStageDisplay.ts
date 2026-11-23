import { formatTime } from '@/utils/format'
import type { GenerationChainStage } from '../api/generationChain.api'

const labels: Record<string, string> = { approved: '已采用', draft: '有候选', invalid: '来源失效', running: '运行中', failed: '执行失败', not_started: '未开始', imported: '已导入' }
export function generationStageLabel(stage: GenerationChainStage) {
  return labels[stage.state] ?? stage.state
}
export function generationFailureMeta(stage: GenerationChainStage) {
  return [
    stage.failureRunId ? `运行 ID：${stage.failureRunId}` : '',
    stage.failedAt ? `失败时间：${formatTime(stage.failedAt)}` : '',
  ].filter(Boolean).join(' · ')
}
export function generationStageClass(stage: GenerationChainStage) {
  if (stage.state === 'running') return 'is-running'
  return ({ running: 'is-running', failed: 'is-failed', imported: 'is-imported', approved: 'is-approved', draft: 'is-draft', invalid: 'is-invalid' } as Record<string, string>)[stage.state] ?? 'is-empty'
}
