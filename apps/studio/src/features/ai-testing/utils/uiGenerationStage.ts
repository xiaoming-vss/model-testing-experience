import type { UiCaseGenerateTaskRun } from '../types'

export const uiGenerationStages = [
  { key: 'ui_surface', label: '元素控件清单', field: 'uiSurface', language: 'json' },
  { key: 'ui_design', label: 'UI 用例设计', field: 'uiDesign', language: 'json' },
  { key: 'ui_yaml', label: '用例 YAML', field: null, language: 'yaml' },
] as const

export type UiGenerationStage = typeof uiGenerationStages[number]['key']

export function uiStageMeta(stage: UiGenerationStage) {
  return uiGenerationStages.find(item => item.key === stage)!
}

export function currentUiGenerationStage(run: UiCaseGenerateTaskRun): UiGenerationStage {
  return run.currentStage === 'completed' ? 'ui_yaml' : run.currentStage as UiGenerationStage
}

export function uiStageArtifactText(run: UiCaseGenerateTaskRun, stage: UiGenerationStage): string {
  const info = uiStageMeta(stage)
  if (!info.field) return run.resultYaml ?? ''
  const config = run.configJson && typeof run.configJson === 'object' ? run.configJson as Record<string, unknown> : {}
  const value = config[info.field]
  return value == null ? '' : typeof value === 'string' ? value : JSON.stringify(value, null, 2)
}

export function uiStageHasContent(run: UiCaseGenerateTaskRun, stage: UiGenerationStage): boolean {
  return Boolean(uiStageArtifactText(run, stage))
}

export function uiStageEditable(run: UiCaseGenerateTaskRun, stage: UiGenerationStage): boolean {
  const waiting = run.status === 'waiting_review' || (stage === 'ui_yaml' && run.status === 'success')
  return stage === currentUiGenerationStage(run) && waiting && run.reviewStatus === 'pending' && run.importStatus !== 'imported'
}
